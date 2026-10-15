"""Step 2: do clubs pay more than market value, and what drives the premium?

Premium = transfer fee / pre-transfer market value, analysed on the log scale
(log premium 0 = paid exactly market value; +0.1 is roughly 10% over).

Outputs
  outputs/02_premium_by_group.csv     descriptive medians by buying league, age band, window
  outputs/02_regression.csv           OLS coefficients, converted to % premium
  figures/02_transfer_premium.png     buying-league premiums over time + regression effects

Model (OLS, standard errors clustered by buying club):
  log_premium ~ buying league + selling league + age band + position
               + log market value + deadline week + winter window + season fixed effects
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import statsmodels.formula.api as smf

from common import FIG_DIR, OUT_DIR, ROOT, connect

LEAGUE_NAMES = {"GB1": "Premier League", "ES1": "LaLiga", "IT1": "Serie A",
                "L1": "Bundesliga", "FR1": "Ligue 1", "Other": "Other leagues"}
COLORS = {"GB1": "#7b2cbf", "ES1": "#e07b39", "IT1": "#2a6fdb", "L1": "#d62839",
          "FR1": "#3a9e5f", "Other": "#8d8d8d"}


def load(con):
    sql = Path(ROOT / "sql" / "02_paid_transfers.sql").read_text()
    df = con.execute(sql).df()
    # The model also uses buying club for clustering.
    return df


def pct(x):
    return f"{(np.exp(x) - 1) * 100:+.1f}%"


def describe(df):
    rows = []
    for col in ["buy_group", "sell_group", "age_band", "position", "deadline_week", "winter_window"]:
        g = df.groupby(col)["log_premium"].agg(n="count", median="median", mean="mean")
        g["share_overpaid"] = df.groupby(col)["log_premium"].apply(lambda s: (s > 0).mean())
        g = g.reset_index().rename(columns={col: "level"})
        g.insert(0, "factor", col)
        rows.append(g)
    import pandas as pd
    return pd.concat(rows, ignore_index=True)


def regress(df):
    df = df.assign(log_mv=np.log(df["market_value"]),
                   deadline_week=df["deadline_week"].astype(int),
                   winter_window=df["winter_window"].astype(int))
    formula = ("log_premium ~ C(buy_group, Treatment('Other')) + C(sell_group, Treatment('Other'))"
               " + C(age_band, Treatment('24-26')) + C(position, Treatment('Midfield'))"
               " + log_mv + deadline_week + winter_window + C(season_start)")
    groups = df["to_club_name"].fillna("unknown").astype("category").cat.codes
    model = smf.ols(formula, data=df).fit(cov_type="cluster", cov_kwds={"groups": groups})
    tab = model.summary2().tables[1].reset_index().rename(columns={"index": "term"})
    tab = tab[~tab["term"].str.startswith("C(season_start")]
    tab["effect_pct"] = (np.exp(tab["Coef."]) - 1) * 100
    return model, tab


def plot(df, tab):
    FIG_DIR.mkdir(exist_ok=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.5), gridspec_kw={"width_ratios": [1.15, 1]})

    # Left: median premium by buying league over time (3-season rolling to smooth noise).
    # The latest season is still in progress, so it is left out of the trend line.
    done = df[df["season_start"] < df["season_start"].max()]
    trend = (done.groupby(["buy_group", "season_start"])["log_premium"].median().unstack(0)
             .sort_index().rolling(3, min_periods=2).median())
    for lg in ["GB1", "ES1", "IT1", "L1", "FR1", "Other"]:
        if lg in trend:
            a1.plot(trend.index, (np.exp(trend[lg]) - 1) * 100, label=LEAGUE_NAMES[lg],
                    color=COLORS[lg], lw=2.4 if lg == "GB1" else 1.6)
    a1.axhline(0, color="#444", lw=0.8)
    a1.set(title="Median fee vs. market value, by buying league\n(3-season rolling median)",
           xlabel="Season (start year)", ylabel="Fee relative to market value (%)")
    a1.legend(frameon=False, fontsize=9, ncol=2)

    # Right: regression effects with 95% CI.
    keep = tab[~tab["term"].isin(["Intercept"])].copy()
    pretty = (keep["term"]
              .str.replace(r"C\(buy_group, Treatment\('Other'\)\)\[T\.(\w+)\]",
                           lambda m: "Buyer: " + LEAGUE_NAMES[m.group(1)], regex=True)
              .str.replace(r"C\(sell_group, Treatment\('Other'\)\)\[T\.(\w+)\]",
                           lambda m: "Seller: " + LEAGUE_NAMES[m.group(1)], regex=True)
              .str.replace(r"C\(age_band, Treatment\('24-26'\)\)\[T\.(.+)\]", r"Age \1 (vs 24-26)", regex=True)
              .str.replace(r"C\(position, Treatment\('Midfield'\)\)\[T\.(\w+)\]", r"\1 (vs Midfield)", regex=True)
              .replace({"log_mv": "log market value (per unit)", "deadline_week": "Deadline week",
                        "winter_window": "Winter window"}))
    keep["label"] = pretty
    keep = keep.iloc[::-1]
    lo = (np.exp(keep["[0.025"]) - 1) * 100
    hi = (np.exp(keep["0.975]"]) - 1) * 100
    y = np.arange(len(keep))
    a2.errorbar(keep["effect_pct"], y, xerr=[keep["effect_pct"] - lo, hi - keep["effect_pct"]],
                fmt="o", color="#2a6fdb", ecolor="#9bbcf0", capsize=2, ms=4)
    a2.axvline(0, color="#444", lw=0.8)
    a2.set_yticks(y, keep["label"], fontsize=8.5)
    a2.set(title="What drives the premium (OLS, 95% CI)\nreference: other leagues, age 24-26, midfield",
           xlabel="Effect on fee relative to market value (%)")

    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    path = FIG_DIR / "02_transfer_premium.png"
    fig.savefig(path, dpi=160)
    return path


def main():
    con = connect()
    df = load(con)
    print(f"{len(df):,} paid transfers, seasons {df['season_start'].min()}-{df['season_start'].max()}")
    print(f"Overall median premium: {pct(df['log_premium'].median())}; "
          f"share paid above market value: {(df['log_premium'] > 0).mean():.1%}")

    OUT_DIR.mkdir(exist_ok=True)
    desc = describe(df)
    desc.to_csv(OUT_DIR / "02_premium_by_group.csv", index=False)
    print("\nMedian premium by buying league")
    for _, r in desc[desc["factor"] == "buy_group"].iterrows():
        print(f"  {LEAGUE_NAMES[r['level']]:<15} n={r['n']:>6,}  median {pct(r['median'])}  "
              f"overpaid {r['share_overpaid']:.0%}")

    model, tab = regress(df)
    tab.to_csv(OUT_DIR / "02_regression.csv", index=False)
    print(f"\nRegression: n={int(model.nobs):,}, R^2={model.rsquared:.3f}")
    for _, r in tab.iterrows():
        if r["term"] == "Intercept":
            continue
        star = "***" if r["P>|z|"] < 0.001 else "**" if r["P>|z|"] < 0.01 else "*" if r["P>|z|"] < 0.05 else ""
        print(f"  {r['term'][:60]:<60} {r['effect_pct']:+7.1f}% {star}")

    print(f"\nFigure: {plot(df, tab)}")


if __name__ == "__main__":
    main()
