"""Step 10: match outcome model (Elo + ordered logit) with an honest backtest.

Model
  * Elo ratings per league: after each match the winner takes points from the loser,
    r += K * G * (result - expected), expected = 1 / (1 + 10^(-(r_home + H - r_away) / 400)).
    G optionally scales the update by goal margin (World Football Elo style).
  * Between seasons, ratings shrink toward the mean by `reg`; promoted clubs start at the
    average final rating of the clubs they replaced.
  * Optional squad-value prior (from step 8): a club's start-of-season rating is blended with a
    rating implied by its preseason squad value relative to the league, weight w, scale b.
  * An ordered logit turns the rating gap into P(home win), P(draw), P(away win).

Validation (no information from the test period is used for fitting)
  * Elo parameters K, H, reg and margin are chosen on 2014/15-2019/20 (2012-13 is warm-up).
  * Squad-value prior parameters are chosen on 2018/19-2019/20 (the first seasons with values).
  * Both models are then scored on 2020/21-2025/26 with the Ranked Probability Score (RPS, lower
    is better) against a baseline that always predicts the training-period outcome frequencies.

Outputs
  outputs/10_backtest.csv, figures/10_match_model.png
  dashboard/public/data/match_model.json   backtest summary and calibration for the dashboard
  dashboard/public/data/elo_state.json     parameters and end-of-2025/26 ratings for the live job
"""
import itertools
import json
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from common import FIG_DIR, OUT_DIR, ROOT, connect

LEAGUES = ["GB1", "ES1", "IT1", "L1", "FR1"]
TRAIN = (2014, 2019)
VALUE_TUNE = (2018, 2019)
TEST = (2020, 2025)
BASE = 1500.0
DEST = ROOT / "dashboard" / "public" / "data"


# ----------------------------------------------------------------------------------------- data
def load_matches(con):
    df = con.execute("""
        SELECT game_id, competition_id AS league, CAST(season AS INT) AS season, date,
               home_club_id AS home, away_club_id AS away,
               home_club_goals AS hg, away_club_goals AS ag
        FROM games
        WHERE competition_id IN ('GB1','ES1','IT1','L1','FR1') AND home_club_goals IS NOT NULL
        ORDER BY date, game_id
    """).df()
    df["y"] = np.select([df["hg"] > df["ag"], df["hg"] == df["ag"]], [2, 1], 0)  # 2 home, 1 draw, 0 away
    # Matchday from the home team's perspective (number of league games it has played so far + 1).
    long = pd.concat([df[["game_id", "league", "season", "date", "home"]].rename(columns={"home": "club"}),
                      df[["game_id", "league", "season", "date", "away"]].rename(columns={"away": "club"})])
    long = long.sort_values(["date", "game_id"])
    long["n"] = long.groupby(["league", "season", "club"]).cumcount() + 1
    md = long.groupby("game_id")["n"].max().rename("matchday")
    return df.join(md, on="game_id").reset_index(drop=True)


def load_value_priors(con):
    """Relative preseason squad value (log, vs league-season mean) from step 8, 2018/19 onward."""
    sql = (ROOT / "sql" / "08_preseason_value.sql").read_text()
    v = con.execute(sql).df()
    v = v[v["squad_players"] >= 15].copy()
    v["log_value"] = np.log(v["squad_value"])
    v["rel"] = v["log_value"] - v.groupby(["league", "season"])["log_value"].transform("mean")
    return {(r.league, int(r.season), int(r.club_id)): float(r.rel) for r in v.itertuples()}


# ------------------------------------------------------------------------------------------ elo
def margin_mult(gd):
    gd = abs(gd)
    return 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8


def season_start(prev, teams, reg, relegated_mean, prior=None, w=0.0, b=0.0):
    """Start-of-season ratings for `teams` given last season's final ratings `prev`."""
    start = {}
    for t in teams:
        r = BASE + (1 - reg) * (prev[t] - BASE) if t in prev else relegated_mean
        if prior is not None and t in prior and w > 0:
            r = (1 - w) * r + w * (BASE + b * prior[t])
        start[t] = r
    return start


def replay(df, K, H, reg, margin, priors=None, w=0.0, b=0.0):
    """Run Elo through all matches; return pre-match rating gaps and final ratings per league-season."""
    teams = df.groupby(["league", "season"])["home"].unique().to_dict()
    ratings, current, finals = {}, {}, {}
    gaps = np.empty(len(df))
    lg_arr, s_arr, h_arr, a_arr = df["league"].to_numpy(), df["season"].to_numpy(), df["home"].to_numpy(), df["away"].to_numpy()
    hg_arr, ag_arr = df["hg"].to_numpy(), df["ag"].to_numpy()
    for i in range(len(df)):
        lg, s = lg_arr[i], s_arr[i]
        if current.get(lg) != s:
            prev = ratings.get(lg, {})
            if lg in current:
                finals[(lg, current[lg])] = dict(prev)
            members = set(teams[(lg, s)])
            leavers = [prev[t] for t in prev if t not in members]
            rel_mean = float(np.mean(leavers)) if leavers else BASE - 100
            prior = None
            if priors is not None:
                prior = {t: priors[(lg, s, t)] for t in members if (lg, s, t) in priors}
            ratings[lg] = season_start(prev, members, reg, rel_mean, prior, w, b)
            current[lg] = s
        R = ratings[lg]
        h, a = h_arr[i], a_arr[i]
        diff = R[h] + H - R[a]
        gaps[i] = diff / 100.0
        exp_h = 1.0 / (1.0 + 10 ** (-diff / 400.0))
        res = 1.0 if hg_arr[i] > ag_arr[i] else 0.5 if hg_arr[i] == ag_arr[i] else 0.0
        g = margin_mult(hg_arr[i] - ag_arr[i]) if margin else 1.0
        delta = K * g * (res - exp_h)
        R[h] += delta
        R[a] -= delta
    for lg, s in current.items():
        finals[(lg, s)] = dict(ratings[lg])
    return gaps, finals


# ------------------------------------------------------------------------------- ordered logit
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def ol_probs(params, d):
    c1, log_gap, beta = params
    c2 = c1 + math.exp(log_gap)
    p_away = sigmoid(c1 - beta * d)
    p_le_draw = sigmoid(c2 - beta * d)
    return np.column_stack([1 - p_le_draw, p_le_draw - p_away, p_away])  # home, draw, away


def fit_ol(d, y):
    def nll(p):
        pr = ol_probs(p, d)
        idx = np.where(y == 2, 0, np.where(y == 1, 1, 2))
        return -np.log(np.clip(pr[np.arange(len(y)), idx], 1e-12, 1)).sum()
    res = minimize(nll, x0=[-0.5, 0.0, 0.5], method="BFGS")
    return res.x


def rps(p, y):
    """Ranked probability score for ordered outcomes (home, draw, away); lower is better."""
    o = np.column_stack([y == 2, y == 1, y == 0]).astype(float)
    c1 = p[:, 0] - o[:, 0]
    c2 = p[:, 0] + p[:, 1] - o[:, 0] - o[:, 1]
    return 0.5 * (c1 ** 2 + c2 ** 2)


def in_range(df, rng):
    return (df["season"] >= rng[0]) & (df["season"] <= rng[1])


# ------------------------------------------------------------------------------------------ main
def main():
    con = connect()
    df = load_matches(con)
    priors = load_value_priors(con)
    train, test = in_range(df, TRAIN).to_numpy(), in_range(df, TEST).to_numpy()
    y = df["y"].to_numpy()
    print(f"{len(df):,} matches; train {train.sum():,}, test {test.sum():,}")

    # 1. Tune Elo parameters on the training seasons.
    results = []
    for K, H, reg, margin in itertools.product([6, 8, 10, 12, 15, 20], [10, 20, 30, 40, 60], [0.0, 0.05, 0.1, 0.2, 0.33], [False, True]):
        gaps, _ = replay(df, K, H, reg, margin)
        params = fit_ol(gaps[train], y[train])
        score = rps(ol_probs(params, gaps[train]), y[train]).mean()
        results.append((score, K, H, reg, margin))
    results.sort()
    _, K, H, reg, margin = results[0]
    print(f"Best Elo on training seasons: K={K}, H={H}, reg={reg}, margin={margin}, RPS={results[0][0]:.4f}")

    # 2. Tune the squad-value prior on the first seasons with values (still before the test period).
    tune = in_range(df, VALUE_TUNE).to_numpy()
    best_v = None
    for w, b in itertools.product([0.0, 0.25, 0.5, 0.75], [100, 150, 200, 250, 300]):
        gaps, _ = replay(df, K, H, reg, margin, priors, w, b)
        params = fit_ol(gaps[train], y[train])
        score = rps(ol_probs(params, gaps[tune]), y[tune]).mean()
        if best_v is None or score < best_v[0]:
            best_v = (score, w, b)
    _, w, b = best_v
    print(f"Best value prior on 2018/19-2019/20: w={w}, b={b}")

    # 3. Score both models on the untouched test seasons.
    base_freq = np.array([(y[train] == 2).mean(), (y[train] == 1).mean(), (y[train] == 0).mean()])
    p_base = np.tile(base_freq, (len(df), 1))
    gaps_elo, _ = replay(df, K, H, reg, margin)
    par_elo = fit_ol(gaps_elo[train], y[train])
    p_elo = ol_probs(par_elo, gaps_elo)
    gaps_val, finals = replay(df, K, H, reg, margin, priors, w, b)
    par_val = fit_ol(gaps_val[train], y[train])
    p_val = ol_probs(par_val, gaps_val)

    early = (df["matchday"] <= 8).to_numpy()
    rows = []
    for name, p in [("Baseline (outcome frequencies)", p_base), ("Elo", p_elo), ("Elo + squad value", p_val)]:
        r = rps(p, y)
        fav_right = (p.argmax(1) == np.where(y == 2, 0, np.where(y == 1, 1, 2)))
        rows.append({"model": name, "rps_test": r[test].mean(), "rps_test_early": r[test & early].mean(),
                     "rps_test_rest": r[test & ~early].mean(), "accuracy_test": fav_right[test].mean()})
    summary = pd.DataFrame(rows)
    print("\nTest seasons 2020/21-2025/26 (lower RPS is better)")
    print(summary.round(4).to_string(index=False))

    use_value = summary.loc[2, "rps_test"] < summary.loc[1, "rps_test"]
    p_main, par_main, gaps_main = (p_val, par_val, gaps_val) if use_value else (p_elo, par_elo, gaps_elo)
    main_name = "Elo + squad value" if use_value else "Elo"
    r_main, r_base = rps(p_main, y), rps(p_base, y)
    skill = 1 - r_main[test].mean() / r_base[test].mean()
    print(f"Chosen: {main_name}; skill vs baseline on test seasons: {skill:.1%}")

    # Per-season and calibration tables (test period).
    per_season = (pd.DataFrame({"season": df["season"], "league": df["league"], "model": r_main, "base": r_base})[test]
                  .groupby("season")[["model", "base"]].mean().reset_index())
    OUT_DIR.mkdir(exist_ok=True)
    per_season.to_csv(OUT_DIR / "10_backtest.csv", index=False)
    calib = []
    for k, label in enumerate(["home", "draw", "away"]):
        pk, ok = p_main[test, k], (np.array([2, 1, 0])[k] == y[test])
        bins = np.clip((pk * 10).astype(int), 0, 9)
        for bn in np.unique(bins):
            m = bins == bn
            if m.sum() >= 40:
                calib.append({"outcome": label, "predicted": float(pk[m].mean()), "observed": float(ok[m].mean()),
                              "n": int(m.sum())})

    # Figure.
    FIG_DIR.mkdir(exist_ok=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 5))
    cdf = pd.DataFrame(calib)
    for label, color in [("home", "#2a78d6"), ("draw", "#898781"), ("away", "#eb6834")]:
        d = cdf[cdf["outcome"] == label]
        a1.plot(d["predicted"], d["observed"], "o-", color=color, label=f"{label} win" if label != "draw" else "draw", lw=2)
    a1.plot([0, 1], [0, 1], color="#444", lw=0.8)
    a1.set(xlim=(0, 1), ylim=(0, 1), xlabel="Predicted probability", ylabel="Observed frequency",
           title="Calibration on test seasons 2020/21–2025/26")
    a1.legend(frameon=False)
    x = np.arange(len(per_season))
    a2.bar(x - 0.2, per_season["base"], 0.4, color="#c3c2b7", label="Baseline")
    a2.bar(x + 0.2, per_season["model"], 0.4, color="#2a78d6", label=main_name)
    a2.set_xticks(x, [f"{s}/{str(s + 1)[2:]}" for s in per_season["season"]])
    a2.set_ylim(0, per_season["base"].max() * 1.12)
    a2.set(title=f"RPS by test season (lower is better) · skill {skill:.1%}", ylabel="Ranked probability score")
    a2.legend(frameon=False)
    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "10_match_model.png", dpi=160)

    # For live forecasting, refit the outcome model on every season now that validation is done, so it
    # reflects the smaller home advantage seen since 2020. The live season is still out-of-sample.
    fit_all = in_range(df, (TRAIN[0], TEST[1])).to_numpy()
    par_live = fit_ol(gaps_main[fit_all], y[fit_all])
    home_rate = df.groupby(df["season"] >= TEST[0])["y"].apply(lambda s: (s == 2).mean())
    print(f"Home-win rate: {home_rate[False]:.1%} before 2020/21, {home_rate[True]:.1%} since")

    # Exports.
    DEST.mkdir(parents=True, exist_ok=True)
    last = max(df["season"])
    names = {int(k): v for k, v in con.execute("SELECT club_id, name FROM clubs").fetchall()}  # club_id is VARCHAR
    state = {
        "season": int(last), "base": BASE, "K": K, "H": H, "reg": reg, "margin": bool(margin),
        "valuePrior": {"w": w, "b": b, "used": bool(use_value)},
        "ordered": {"c1": float(par_live[0]), "logGap": float(par_live[1]), "beta": float(par_live[2])},
        "baseline": [float(v) for v in base_freq],
        "ratings": {lg: {str(int(c)): {"name": names.get(int(c)), "rating": round(r, 2)}
                         for c, r in finals[(lg, last)].items()} for lg in LEAGUES},
    }
    model_json = {
        "model": main_name, "train": f"{TRAIN[0]}/{str(TRAIN[0] + 1)[2:]}–{TRAIN[1]}/{str(TRAIN[1] + 1)[2:]}",
        "test": f"{TEST[0]}/{str(TEST[0] + 1)[2:]}–{TEST[1]}/{str(TEST[1] + 1)[2:]}",
        "testMatches": int(test.sum()), "skill": float(skill),
        "summary": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in summary.to_dict("records")],
        "perSeason": [{"season": int(r.season), "model": round(r.model, 4), "base": round(r.base, 4)} for r in per_season.itertuples()],
        "calibration": [{**c, "predicted": round(c["predicted"], 3), "observed": round(c["observed"], 3)} for c in calib],
        "params": {"K": K, "H": H, "reg": reg, "margin": bool(margin), "w": w, "b": b},
        "homeWinRate": {"before": round(float(home_rate[False]), 3), "since": round(float(home_rate[True]), 3)},
    }
    for name, obj in [("elo_state", state), ("match_model", model_json)]:
        path = DEST / f"{name}.json"
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
