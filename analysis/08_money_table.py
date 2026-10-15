"""Step 8: how well does preseason squad value predict the league table?

For every big-five club-season 2018/19-2025/26, compare the squad's market value on 31 August with
its final points per game.

Model: OLS of points per game on relative squad value, log(club value) minus the league-season mean
of log values, with league fixed effects. Relative value removes inflation and league wealth, so the
same model works for any season, including the one in progress (see 09_live_standings.py).
Accuracy is checked with leave-one-season-out validation: each season is predicted by a model fitted
on the other seasons.

Outputs
  outputs/08_money_table.csv          every club-season with expected and actual points
  figures/08_money_table.png          relative squad value vs points per game
  dashboard/public/data/money_history.json   seasons, model and over/under-performers for the dashboard
  dashboard/public/data/preseason_live.json  squad values for the season in progress (latest valuations)
"""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import FIG_DIR, OUT_DIR, ROOT, connect

LEAGUES = {"GB1": "Premier League", "ES1": "LaLiga", "IT1": "Serie A", "L1": "Bundesliga", "FR1": "Ligue 1"}
COLORS = {"GB1": "#2a78d6", "ES1": "#eb6834", "IT1": "#1baf7a", "L1": "#eda100", "FR1": "#e87ba4"}
MIN_PLAYERS = 15  # squads with fewer valued players are flagged and left out of the fit
DEST = ROOT / "dashboard" / "public" / "data"


def season_label(s):
    return f"{s}/{str(s + 1)[2:]}"


def load(con):
    df = con.execute((ROOT / "sql" / "08_preseason_value.sql").read_text()).df()
    df["complete"] = df["squad_players"] >= MIN_PLAYERS
    df["log_value"] = np.where(df["squad_value"] > 0, np.log(df["squad_value"].clip(lower=1)), np.nan)
    mean_log = df[df["complete"]].groupby(["league", "season"])["log_value"].mean().rename("mean_log")
    df = df.join(mean_log, on=["league", "season"])
    df["rel_value"] = df["log_value"] - df["mean_log"]
    return df


def fit(df):
    d = df[df["complete"]]
    model = smf.ols("ppg ~ rel_value + C(league)", data=d).fit(cov_type="HC1")
    df = df.copy()
    df["exp_ppg"] = model.predict(df)

    # Leave-one-season-out: predict each season from the others.
    oos = []
    for s in sorted(d["season"].unique()):
        m = smf.ols("ppg ~ rel_value + C(league)", data=d[d["season"] != s]).fit()
        held = d[d["season"] == s]
        oos.append(pd.Series(m.predict(held), index=held.index))
    oos = pd.concat(oos)
    r2_oos = 1 - ((d["ppg"] - oos) ** 2).sum() / ((d["ppg"] - d["ppg"].mean()) ** 2).sum()

    df["exp_points"] = df["exp_ppg"] * df["played"]
    df["diff"] = df["points"] - df["exp_points"]
    rho = d.groupby(["league", "season"]).apply(
        lambda g: g["squad_value"].rank().corr(g["points"].rank())).mean()
    stats = {
        "slope": float(model.params["rel_value"]),
        "intercepts": {lg: float(model.params["Intercept"] + model.params.get(f"C(league)[T.{lg}]", 0.0))
                       for lg in LEAGUES},
        "r2": float(model.rsquared),
        "r2OutOfSample": float(r2_oos),
        "rankCorr": float(rho),
        "n": int(model.nobs),
        "seasons": f"{season_label(int(d['season'].min()))}–{season_label(int(d['season'].max()))}",
    }
    return df, stats


def plot(df, stats):
    FIG_DIR.mkdir(exist_ok=True)
    d = df[df["complete"]]
    fig, ax = plt.subplots(figsize=(10, 6))
    for lg, name in LEAGUES.items():
        x = d[d["league"] == lg]
        ax.scatter(np.exp(x["rel_value"]), x["ppg"], s=16, alpha=0.55, color=COLORS[lg], label=name, linewidths=0)
    xs = np.linspace(d["rel_value"].min(), d["rel_value"].max(), 100)
    mean_int = np.mean(list(stats["intercepts"].values()))
    ax.plot(np.exp(xs), mean_int + stats["slope"] * xs, color="#444", lw=1.5, label="Fit (average league)")
    for _, r in pd.concat([d.nlargest(4, "diff"), d.nsmallest(2, "diff")]).iterrows():
        ax.annotate(f"{r['club']} {season_label(r['season'])} ({r['diff']:+.0f} pts)",
                    (np.exp(r["rel_value"]), r["ppg"]), fontsize=8, xytext=(6, 4), textcoords="offset points")
    ax.set_xscale("log")
    ax.set(title=f"Preseason squad value vs. points per game, big-five leagues {stats['seasons']}\n"
                 f"R² {stats['r2']:.2f} (out-of-sample {stats['r2OutOfSample']:.2f})",
           xlabel="Squad value relative to league average (×, log scale)", ylabel="Points per game")
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    path = FIG_DIR / "08_money_table.png"
    fig.savefig(path, dpi=160)
    return path


def preseason_live(con):
    """Squad values for the season in progress: each player's latest valuation and the club on it."""
    q = con.execute("""
        WITH v AS (
            SELECT player_id, current_club_id AS club_id, current_club_name AS vname,
                   market_value_in_eur AS value, date
            FROM player_valuations
            WHERE market_value_in_eur > 0
            QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY date DESC, market_value_in_eur DESC) = 1
        )
        SELECT v.club_id, COALESCE(c.name, ANY_VALUE(v.vname)) AS club, c.domestic_competition_id AS league,
               SUM(v.value) AS squad_value, COUNT(*) AS squad_players, MAX(v.date) AS last_date
        FROM v LEFT JOIN clubs c ON c.club_id = v.club_id
        WHERE v.date >= (SELECT MAX(date) FROM player_valuations) - INTERVAL 9 MONTH
        GROUP BY v.club_id, c.name, c.domestic_competition_id
        HAVING COUNT(*) >= 3
        ORDER BY squad_value DESC
    """).df()
    as_of = con.execute("SELECT strftime(MAX(date), '%Y-%m-%d') FROM player_valuations").fetchone()[0]
    return {
        "valuesAsOf": as_of,
        "minPlayers": MIN_PLAYERS,
        "clubs": [{"id": int(r.club_id), "name": r.club, "league": r.league if isinstance(r.league, str) else None,
                   "value": int(r.squad_value),
                   "players": int(r.squad_players)} for r in q.itertuples()],
    }


def main():
    con = connect()
    df, stats = fit(load(con))
    OUT_DIR.mkdir(exist_ok=True)
    df.to_csv(OUT_DIR / "08_money_table.csv", index=False)

    print(f"{stats['n']} club-seasons, {stats['seasons']}")
    print(f"R² {stats['r2']:.3f}, out-of-sample {stats['r2OutOfSample']:.3f}, "
          f"mean within-season rank correlation {stats['rankCorr']:.3f}")
    print(f"Slope: doubling relative squad value adds {stats['slope'] * np.log(2):.2f} points per game "
          f"(~{stats['slope'] * np.log(2) * 38:.0f} points over 38 games)")
    d = df[df["complete"]]
    show = ["league", "season", "club", "points", "exp_points", "diff", "squad_value"]
    print("\nBiggest overperformers\n", d.nlargest(8, "diff")[show].round(1).to_string(index=False))
    print("\nBiggest underperformers\n", d.nsmallest(8, "diff")[show].round(1).to_string(index=False))
    print(f"\nFigure: {plot(df, stats)}")

    DEST.mkdir(parents=True, exist_ok=True)
    history = {
        "model": stats,
        "minPlayers": MIN_PLAYERS,
        "rows": [{"league": r.league, "season": int(r.season), "club": r.club, "id": int(r.club_id),
                  "played": int(r.played), "points": int(r.points), "gd": int(r.goal_diff),
                  "value": int(r.squad_value), "players": int(r.squad_players), "complete": bool(r.complete),
                  "expPoints": None if np.isnan(r.exp_points) else round(float(r.exp_points), 1),
                  "diff": None if np.isnan(r.diff) else round(float(r.diff), 1)}
                 for r in df.itertuples()],
    }
    live = preseason_live(con)
    for name, obj in [("money_history", history), ("preseason_live", live)]:
        path = DEST / f"{name}.json"
        # allow_nan=False: fail loudly rather than write NaN, which browsers cannot parse.
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1e3:.0f} KB")
    print(f"Live-season squads: {len(live['clubs'])} clubs, values as of {live['valuesAsOf']}")


if __name__ == "__main__":
    main()
