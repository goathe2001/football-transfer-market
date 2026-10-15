"""Step 3: does scoring or assisting at a major tournament raise a player's market value?

Design: event study with matched comparison groups.
  * Panel: every valuation of eligible players from 12 months before kickoff to 12 months after
    the final, expressed as the log change from the player's last pre-tournament value.
  * Treated: players with at least one goal or assist at the tournament.
  * Controls: other international-level players valued before the same tournament.
  * Comparisons are made within cells of tournament x position x age band x pre-value quintile, so
    a 24-year-old EUR 30m attacker is compared with other 24-year-old EUR 30m attackers.
  * For each quarter of event time, regress log change on treatment with cell fixed effects,
    standard errors clustered by player. Pre-tournament quarters act as a placebo check: treated
    and control players should be on the same path before the tournament.

Outputs
  outputs/03_event_study.csv, outputs/03_dose_response.csv, figures/03_world_cup_effect.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import FIG_DIR, OUT_DIR, ROOT, connect


def load(con):
    df = con.execute((ROOT / "sql" / "03_tournament_panel.sql").read_text()).df()
    df["age_band"] = pd.cut(df["age"], [17, 21, 24, 27, 30, 35],
                            labels=["18-21", "22-24", "25-27", "28-30", "31-34"])
    players = df.drop_duplicates(["tournament", "player_id"])
    q = players.groupby("tournament")["pre_value"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    df = df.merge(players[["tournament", "player_id"]].assign(value_q=q.values),
                  on=["tournament", "player_id"])
    df["cell"] = (df["tournament"] + "|" + df["position"] + "|" + df["age_band"].astype(str)
                  + "|" + df["value_q"].astype(str))
    # Pre-tournament momentum: change from the earliest valuation 9-12 months before kickoff to the
    # baseline. Scorers tend to be players already in form; matching on this removes that pre-trend.
    q4 = (df[df["quarter"] == -4].sort_values("date").groupby(["tournament", "player_id"])["log_change"]
          .first().mul(-1).rename("momentum").reset_index())
    df = df.merge(q4, on=["tournament", "player_id"], how="left")
    mom = df.drop_duplicates(["tournament", "player_id"])[["tournament", "player_id", "momentum"]].copy()
    mom["mom_t"] = mom.groupby("tournament")["momentum"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["down", "flat", "up"]).astype(str))
    mom["mom_t"] = mom["mom_t"].where(mom["momentum"].notna(), "unknown")
    df = df.merge(mom[["tournament", "player_id", "mom_t"]], on=["tournament", "player_id"])
    df["cell_mom"] = df["cell"] + "|" + df["mom_t"]
    df["treated"] = (df["contributions"] > 0).astype(int)
    df["dose"] = pd.cut(df["contributions"], [-1, 0, 1, 2, 99], labels=["0", "1", "2", "3+"])
    return df


def per_player_quarter(df):
    """One observation per player, tournament and quarter: the last valuation in that quarter."""
    df = df.sort_values("date")
    return df.groupby(["tournament", "player_id", "quarter"], as_index=False).last()


def fit(d, rhs, cell="cell"):
    groups = d["player_id"].astype("category").cat.codes
    return smf.ols(f"log_change ~ {rhs} + C({cell})", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": groups})


def event_study(pq, cell="cell"):
    rows = []
    for qtr in sorted(pq["quarter"].unique()):
        d = pq[pq["quarter"] == qtr]
        # Need treated and control players inside the same cells.
        mixed = d.groupby(cell)["treated"].transform(lambda s: 0 < s.mean() < 1)
        d = d[mixed]
        if d["treated"].sum() < 30:
            continue
        m = fit(d, "treated", cell)
        b, se = m.params["treated"], m.bse["treated"]
        rows.append({"quarter": qtr, "effect": b, "lo": b - 1.96 * se, "hi": b + 1.96 * se,
                     "p": m.pvalues["treated"], "n_treated": int(d["treated"].sum()),
                     "n_control": int((1 - d["treated"]).sum())})
    return pd.DataFrame(rows)


def dose_response(pq, quarters=(2, 4)):
    rows = []
    for qtr in quarters:
        d = pq[pq["quarter"] == qtr]
        m = fit(d, "C(dose, Treatment('0'))", "cell_mom")
        for lvl in ["1", "2", "3+"]:
            k = f"C(dose, Treatment('0'))[T.{lvl}]"
            rows.append({"quarter": qtr, "contributions": lvl, "effect": m.params[k],
                         "lo": m.conf_int().loc[k, 0], "hi": m.conf_int().loc[k, 1],
                         "n": int((d["dose"] == lvl).sum())})
    return pd.DataFrame(rows)


def pct(x):
    return (np.exp(x) - 1) * 100


def plot(es_val, es, dr):
    FIG_DIR.mkdir(exist_ok=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.5, 5), gridspec_kw={"width_ratios": [1.4, 1]})

    x = es["quarter"]
    a1.axvspan(-0.5, 0.5, color="#f2c14e", alpha=0.25, label="Tournament")
    a1.axhline(0, color="#444", lw=0.8)
    a1.plot(es_val["quarter"], pct(es_val["effect"]), "o--", color="#9a9a9a", lw=1.4,
            label="Matched on value, age, position")
    a1.fill_between(x, pct(es["lo"]), pct(es["hi"]), color="#2a6fdb", alpha=0.15)
    a1.plot(x, pct(es["effect"]), "o-", color="#2a6fdb", lw=2.2,
            label="+ matched on pre-tournament momentum (main)")
    a1.set_xticks(x, [("Q" + str(q)) if q > 0 else ("Q" + str(q) if q < 0 else "During") for q in x])
    a1.set(title="Market value of tournament scorers/assisters vs. matched peers\n"
                 "relative to last pre-tournament value (95% CI)",
           xlabel="Quarters before kickoff (−) / after the final (+)",
           ylabel="Extra change in market value (%)")
    a1.legend(frameon=False, loc="upper left")

    colors = {2: "#9bbcf0", 4: "#2a6fdb"}
    labels = {2: "6 months after", 4: "12 months after"}
    lv = ["1", "2", "3+"]
    w = 0.36
    for i, (qtr, d) in enumerate(dr.groupby("quarter")):
        d = d.set_index("contributions").loc[lv]
        pos = np.arange(len(lv)) + (i - 0.5) * w
        a2.bar(pos, pct(d["effect"]), w, color=colors[qtr], label=labels[qtr])
        a2.errorbar(pos, pct(d["effect"]), yerr=[pct(d["effect"]) - pct(d["lo"]), pct(d["hi"]) - pct(d["effect"])],
                    fmt="none", ecolor="#333", capsize=3, lw=1)
    a2.set_xticks(np.arange(len(lv)), [f"{l} goal contribution{'s' if l != '1' else ''}" for l in lv])
    a2.axhline(0, color="#444", lw=0.8)
    a2.set(title="Dose response: more goals + assists, bigger bump",
           ylabel="Extra change in market value (%)")
    a2.legend(frameon=False)

    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path = FIG_DIR / "03_world_cup_effect.png"
    fig.savefig(path, dpi=160)
    return path


def main():
    con = connect()
    df = load(con)
    players = df.drop_duplicates(["tournament", "player_id"])
    print(f"{len(players):,} player-tournaments ({players['treated'].sum():,} with a goal or assist) "
          f"across {players['tournament'].nunique()} tournaments")
    print(players.groupby("tournament")["treated"].agg(["count", "sum"]).rename(
        columns={"count": "eligible", "sum": "treated"}).to_string())

    pq = per_player_quarter(df)
    es_val = event_study(pq, "cell")
    es = event_study(pq, "cell_mom")
    dr = dose_response(pq)
    OUT_DIR.mkdir(exist_ok=True)
    pd.concat([es_val.assign(spec="value_age_position"), es.assign(spec="plus_momentum")]).assign(
        effect_pct=lambda d: pct(d["effect"])).to_csv(OUT_DIR / "03_event_study.csv", index=False)
    dr.assign(effect_pct=pct(dr["effect"])).to_csv(OUT_DIR / "03_dose_response.csv", index=False)

    for name, e in [("matched on value/age/position", es_val), ("+ momentum (main)", es)]:
      print(f"\nEvent study, {name} (extra % change vs matched peers)")
      for _, r in e.iterrows():
        print(f"    Q{int(r.quarter):+d}  {pct(r.effect):+6.1f}%  [{pct(r.lo):+.1f}, {pct(r.hi):+.1f}]  "
              f"p={r.p:.3f}  treated={r.n_treated} control={r.n_control}")
    print("\nDose response")
    for _, r in dr.iterrows():
        print(f"  Q+{r.quarter} {r.contributions:>2} contrib: {pct(r.effect):+6.1f}%  "
              f"[{pct(r.lo):+.1f}, {pct(r.hi):+.1f}]  n={r.n}")
    print(f"\nFigure: {plot(es_val, es, dr)}")


if __name__ == "__main__":
    main()
