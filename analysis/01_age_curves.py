"""Step 1: market-value age curves by position.

Two estimates, because the naive one is biased:

1. Cross-sectional median: median value of all players at each age. Simple, but suffers from
   survivorship bias: weak players drop out of the data as they age, so the players still valued
   at 34 are unusually good and the curve declines too slowly.
2. Delta method (standard in sports aging-curve research): for each player, take the change in
   log value from one age to the next, average those changes across players, then chain them.
   Every comparison is within the same player, so who drops out no longer distorts the shape.

Usage: python analysis/01_age_curves.py [--big5]
  --big5  only use valuations recorded while the player was at a club in England, Spain, Italy,
          Germany or France.
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np

from common import FIG_DIR, OUT_DIR, connect, require

BIG5 = ("GB1", "ES1", "IT1", "L1", "FR1")
POSITIONS = ["Attack", "Midfield", "Defender", "Goalkeeper"]
MIN_AGE, MAX_AGE = 17, 37
MIN_PLAYERS = 30  # drop age cells with fewer players than this


def load_player_age_values(con, big5: bool):
    """One row per player per whole year of age: that year's median market value."""
    require(con, "players", {"player_id", "date_of_birth", "position"})
    require(con, "player_valuations", {"player_id", "date", "market_value_in_eur"})
    league_filter = ""
    if big5:
        require(con, "player_valuations", {"player_club_domestic_competition_id"})
        league_filter = f"AND v.player_club_domestic_competition_id IN {BIG5}"
    return con.execute(f"""
        WITH v AS (
            SELECT v.player_id,
                   p.position,
                   FLOOR(date_diff('day', p.date_of_birth, v.date) / 365.25)::INT AS age,
                   v.market_value_in_eur AS value
            FROM player_valuations v
            JOIN players p USING (player_id)
            WHERE v.market_value_in_eur > 0
              AND p.date_of_birth IS NOT NULL
              AND p.position IN {tuple(POSITIONS)}
              {league_filter}
        )
        SELECT player_id, position, age, MEDIAN(value) AS value
        FROM v
        WHERE age BETWEEN {MIN_AGE} AND {MAX_AGE}
        GROUP BY ALL
    """).df()


def cross_sectional(df):
    g = df.groupby(["position", "age"])["value"]
    out = g.agg(n="count", median="median",
                q25=lambda s: s.quantile(0.25), q75=lambda s: s.quantile(0.75)).reset_index()
    return out[out["n"] >= MIN_PLAYERS]


def delta_method(df):
    """Average within-player change in log value between consecutive ages, chained into a curve."""
    df = df.sort_values(["player_id", "age"]).copy()
    df["log_v"] = np.log(df["value"])
    nxt = df.groupby("player_id").shift(-1)
    pairs = df.assign(next_age=nxt["age"], next_log_v=nxt["log_v"])
    pairs = pairs[pairs["next_age"] == pairs["age"] + 1]  # consecutive years only
    pairs["delta"] = pairs["next_log_v"] - pairs["log_v"]

    step = (pairs.groupby(["position", "age"])["delta"]
            .agg(n="count", mean_delta="mean").reset_index())
    step = step[step["n"] >= MIN_PLAYERS]

    curves = []
    for pos, s in step.groupby("position"):
        s = s.sort_values("age")
        # Stop at the first gap so the chain never jumps over a missing age.
        s = s[s["age"].diff().fillna(1).eq(1).cumprod().astype(bool)]
        level = np.concatenate([[0.0], s["mean_delta"].cumsum().to_numpy()])
        ages = np.concatenate([[s["age"].iloc[0]], s["age"].to_numpy() + 1])
        rel = np.exp(level - level.max())  # 1.0 = that position's peak
        curves.append({"position": pos, "ages": ages, "relative_value": rel,
                       "peak_age": int(ages[level.argmax()])})
    return step, curves


def plot(cs, curves, suffix):
    FIG_DIR.mkdir(exist_ok=True)
    colors = dict(zip(POSITIONS, ["#2a6fdb", "#e07b39", "#3a9e5f", "#8a5cc2"]))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))

    for pos in POSITIONS:
        d = cs[cs["position"] == pos]
        if d.empty:
            continue
        a1.plot(d["age"], d["median"] / 1e6, label=pos, color=colors[pos], lw=2)
        a1.fill_between(d["age"], d["q25"] / 1e6, d["q75"] / 1e6, color=colors[pos], alpha=0.12)
    a1.set_yscale("log")
    a1.set(title="Cross-sectional: median value by age (band = IQR)",
           xlabel="Age", ylabel="Market value (EUR m, log scale)")
    a1.legend(frameon=False)

    for c in curves:
        a2.plot(c["ages"], c["relative_value"], label=f'{c["position"]} (peak {c["peak_age"]})',
                color=colors[c["position"]], lw=2)
    a2.set(title="Delta method: within-player curve (1.0 = peak)",
           xlabel="Age", ylabel="Value relative to peak")
    a2.legend(frameon=False)

    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path = FIG_DIR / f"01_age_curves{suffix}.png"
    fig.savefig(path, dpi=160)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--big5", action="store_true")
    args = ap.parse_args()
    suffix = "_big5" if args.big5 else ""

    con = connect()
    df = load_player_age_values(con, args.big5)
    print(f"{len(df):,} player-age rows from {df['player_id'].nunique():,} players")

    cs = cross_sectional(df)
    step, curves = delta_method(df)

    OUT_DIR.mkdir(exist_ok=True)
    cs.to_csv(OUT_DIR / f"01_cross_sectional{suffix}.csv", index=False)
    step.to_csv(OUT_DIR / f"01_delta_steps{suffix}.csv", index=False)

    print("\nPeak age by position")
    for c in curves:
        cs_pos = cs[cs["position"] == c["position"]]
        cs_peak = int(cs_pos.loc[cs_pos["median"].idxmax(), "age"]) if not cs_pos.empty else None
        print(f"  {c['position']:<11} delta method: {c['peak_age']}   cross-sectional: {cs_peak}")

    print(f"\nFigure: {plot(cs, curves, suffix)}")


if __name__ == "__main__":
    main()
