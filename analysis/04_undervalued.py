"""Step 4: which players are valued below what their performance predicts, and does it matter?

1. Fair-value model. Gradient boosting predicts a player's season-end market value from what he did
   that season (league minutes, goals and assists per 90, European minutes, club strength, league,
   age, position, physical profile). The target is log value relative to that season's median, so the
   model learns relative worth and is not thrown off by market inflation. A linear model is fitted
   alongside as a baseline.
2. Walk-forward backtest. For each season 2018/19-2024/25 the model is trained only on earlier
   seasons, then predicts that season. Residual = actual - predicted (negative = undervalued). The test:
   do undervalued players' values rise more over the following year, relative to the market?
3. Scouting list for 2025/26, from a model trained on every earlier season.

Outputs
  outputs/04_backtest_deciles.csv, outputs/04_undervalued_2025_26.csv, outputs/04_model_metrics.csv
  figures/04_undervalued.png
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import r2_score

from common import FIG_DIR, OUT_DIR, ROOT, connect

CATS = ["position", "sub_position", "league", "foot"]
NUMS = ["age", "league_minutes", "league_apps", "minute_share", "g90", "a90", "ga90",
        "yellows90", "euro_minutes", "euro_ga90", "club_ppg", "club_gd", "height_in_cm"]
FIRST_TEST, CURRENT = 2018, 2025
# Russian and Ukrainian club values have been structurally depressed since 2022 (war, suspension from
# European competition), a break a model trained on earlier seasons cannot know about. Their players
# would otherwise flood the list as false bargains, so they are excluded from it.
EXCLUDE_FROM_LIST = {"RU1", "UKR1"}
BIG5 = {"GB1": "Premier League", "ES1": "LaLiga", "IT1": "Serie A", "L1": "Bundesliga", "FR1": "Ligue 1"}


def load(con):
    df = con.execute((ROOT / "sql" / "04_player_seasons.sql").read_text()).df()
    # DuckDB's parallel aggregation returns rows in varying order and can differ in the last bits of
    # floating-point averages between runs; either is enough to flip a tree split. Fix the order and
    # round floats so model fits are exactly reproducible.
    df = df.sort_values(["season", "player_id"]).reset_index(drop=True)
    floats = df.select_dtypes("float").columns
    df[floats] = df[floats].round(8)
    m = df["league_minutes"].clip(lower=1)
    df["g90"] = df["goals"] * 90 / m
    df["a90"] = df["assists"] * 90 / m
    df["ga90"] = df["g90"] + df["a90"]
    df["yellows90"] = df["yellows"] * 90 / m
    df["euro_ga90"] = df["euro_goal_contrib"] * 90 / df["euro_minutes"].clip(lower=90)
    df["minute_share"] = (df["league_minutes"] / (df["club_games"] * 90)).clip(upper=1)
    df = df[df["value"].notna()].copy()
    df["log_value"] = np.log(df["value"])
    df["rel_value"] = df["log_value"] - df.groupby("season")["log_value"].transform("median")
    # Next-year growth relative to the typical player that season (removes market-wide inflation).
    g = np.log(df["value_next"]) - df["log_value"]
    df["rel_growth"] = g - g.groupby(df["season"]).transform("median")
    for c in CATS:
        df[c] = df[c].fillna("unknown").astype(str)
    return df


def design(df, cats):
    # Plain float64: pandas nullable dtypes (pd.NA) are converted unreliably by scikit-learn and made
    # model fits differ from run to run.
    X = df[NUMS].astype("float64")
    for c in CATS:
        X[c] = pd.Categorical(df[c], categories=cats[c])
    return X


def fit_predict(train, test):
    cats = {c: sorted(train[c].unique()) for c in CATS}
    gbm = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=31,
                                        min_samples_leaf=40, l2_regularization=1.0,
                                        categorical_features="from_dtype", random_state=0)
    gbm.fit(design(train, cats), train["rel_value"])
    pred = gbm.predict(design(test, cats))

    # Linear baseline: one-hot categoricals + numeric features + age squared.
    def lin(d):
        X = pd.get_dummies(d[CATS], dtype=float).reindex(columns=lin_cols, fill_value=0)
        num = d[NUMS].fillna(train[NUMS].median())
        return pd.concat([X, num, (d["age"] ** 2).rename("age2")], axis=1)
    lin_cols = pd.get_dummies(train[CATS], dtype=float).columns
    ridge = RidgeCV(alphas=[0.1, 1, 10, 100]).fit(lin(train), train["rel_value"])
    return pred, ridge.predict(lin(test))


def walk_forward(df):
    out, metrics = [], []
    for s in range(FIRST_TEST, CURRENT + 1):
        train, test = df[df["season"] < s], df[df["season"] == s].copy()
        test["pred"], test["pred_linear"] = fit_predict(train, test)
        test["residual"] = test["rel_value"] - test["pred"]
        metrics.append({"season": f"{s}/{str(s + 1)[2:]}", "n": len(test),
                        "r2_gbm": r2_score(test["rel_value"], test["pred"]),
                        "r2_linear": r2_score(test["rel_value"], test["pred_linear"]),
                        "median_abs_err_pct": (np.exp(np.abs(test["residual"]).median()) - 1) * 100})
        out.append(test)
    return pd.concat(out), pd.DataFrame(metrics)


def deciles(bt):
    d = bt[bt["season"] < CURRENT].dropna(subset=["rel_growth"]).copy()
    d["decile"] = d.groupby("season")["residual"].transform(lambda s: pd.qcut(s, 10, labels=False) + 1)
    tab = d.groupby("decile")["rel_growth"].agg(n="count", mean="mean", sem="sem", median="median").reset_index()
    rho = d[["residual", "rel_growth"]].corr(method="spearman").iloc[0, 1]
    return d, tab, rho


def scouting_list(bt):
    cur = bt[bt["season"] == CURRENT].copy()
    cur["model_value"] = cur["value"] * np.exp(-cur["residual"])
    cur["gap_pct"] = (cur["model_value"] / cur["value"] - 1) * 100
    pick = cur[(cur["league_minutes"] >= 1500) & (cur["age"] <= 26) & (cur["value"] >= 1e6)
               & ~cur["league"].isin(EXCLUDE_FROM_LIST)]
    cols = ["name", "age", "position", "sub_position", "club_name", "league", "league_minutes",
            "goals", "assists", "ga90", "value", "model_value", "gap_pct", "contract_expiration_date"]
    return cur, pick.sort_values("residual")[cols]


def plot(cur, tab, rho):
    FIG_DIR.mkdir(exist_ok=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.5, 5.2))

    pv = cur["value"] * np.exp(-cur["residual"])
    big5 = cur["league"].isin(BIG5)
    a1.scatter(pv[~big5] / 1e6, cur.loc[~big5, "value"] / 1e6, s=6, alpha=0.25, color="#9a9a9a",
               label="Other leagues")
    a1.scatter(pv[big5] / 1e6, cur.loc[big5, "value"] / 1e6, s=7, alpha=0.4, color="#2a6fdb",
               label="Big-5 leagues")
    lim = [0.05, 300]
    a1.plot(lim, lim, color="#444", lw=0.8)
    a1.set(xscale="log", yscale="log", xlim=lim, ylim=lim,
           title="2025/26: model fair value vs. market value\n(below the line = undervalued)",
           xlabel="Model fair value (EUR m)", ylabel="Transfermarkt market value (EUR m)")
    a1.legend(frameon=False, loc="upper left")

    x = tab["decile"]
    y = (np.exp(tab["mean"]) - 1) * 100
    err = 1.96 * tab["sem"] * 100
    colors = ["#2a6fdb" if d <= 3 else "#d62839" if d >= 8 else "#b9b9b9" for d in x]
    a2.bar(x, y, color=colors, yerr=err, capsize=3, ecolor="#555")
    a2.axhline(0, color="#444", lw=0.8)
    a2.set_xticks(x, ["1\nmost\nunder-\nvalued"] + [str(i) for i in range(2, 10)] + ["10\nmost\nover-\nvalued"])
    a2.set(title=f"Backtest 2018/19–2024/25: next-year value growth\nvs. market, by model residual decile "
                 f"(Spearman ρ = {rho:.2f})",
           ylabel="Value growth over next year vs. market (%)")

    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    path = FIG_DIR / "04_undervalued.png"
    fig.savefig(path, dpi=160)
    return path


def main():
    con = connect()
    df = load(con)
    print(f"{len(df):,} player-seasons (>=900 league minutes), {df['season'].min()}-{df['season'].max()}")

    bt, metrics = walk_forward(df)
    OUT_DIR.mkdir(exist_ok=True)
    metrics.to_csv(OUT_DIR / "04_model_metrics.csv", index=False)
    print("\nWalk-forward accuracy (trained only on earlier seasons)")
    print(metrics.round(3).to_string(index=False))

    d, tab, rho = deciles(bt)
    tab.to_csv(OUT_DIR / "04_backtest_deciles.csv", index=False)
    print(f"\nBacktest: {len(d):,} player-seasons with next-year value; Spearman(residual, growth) = {rho:.3f}")
    for _, r in tab.iterrows():
        print(f"  decile {int(r.decile):>2}: mean {(np.exp(r['mean']) - 1) * 100:+6.1f}%  "
              f"median {(np.exp(r['median']) - 1) * 100:+6.1f}%  n={int(r.n)}")
    for age_band, sub in d.groupby(pd.cut(d["age"], [0, 23, 27, 40], labels=["<=23", "24-27", "28+"])):
        lo = sub[sub["decile"] <= 2]["rel_growth"].mean()
        hi = sub[sub["decile"] >= 9]["rel_growth"].mean()
        print(f"  age {age_band}: bottom-20% minus top-20% growth = {(np.exp(lo) - np.exp(hi)) * 100:+.1f} pts")

    rob = d[~d["league"].isin(EXCLUDE_FROM_LIST)]
    rob_rho = rob[["residual", "rel_growth"]].corr(method="spearman").iloc[0, 1]
    lo, hi = rob[rob["decile"] == 1]["rel_growth"].mean(), rob[rob["decile"] == 10]["rel_growth"].mean()
    print(f"  without Russia/Ukraine: Spearman = {rob_rho:.3f}; decile 1 {(np.exp(lo) - 1) * 100:+.1f}%, "
          f"decile 10 {(np.exp(hi) - 1) * 100:+.1f}%")

    cur, pick = scouting_list(bt)
    pick.to_csv(OUT_DIR / "04_undervalued_2025_26.csv", index=False)
    print(f"\nTop undervalued, 2025/26 (age <= 26, >= 1500 league minutes, value >= EUR 1m):")
    show = pick.head(15).assign(value=lambda x: (x["value"] / 1e6).round(1),
                                model_value=lambda x: (x["model_value"] / 1e6).round(1),
                                gap_pct=lambda x: x["gap_pct"].round(0), ga90=lambda x: x["ga90"].round(2))
    print(show.drop(columns=["sub_position", "contract_expiration_date"]).to_string(index=False))
    print(f"\nFigure: {plot(cur, tab, rho)}")


if __name__ == "__main__":
    main()
