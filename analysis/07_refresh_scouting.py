"""Step 7: rebuild the dashboard's scouting list from the latest data (run on demand from GitHub Actions).

Only the scouting list is refreshed. The research findings (steps 1-5, insights.json, README) stay
frozen on the 2026-06 snapshot so the published numbers never drift.

How the live list is built
  * Stats season: the most recent season in which at least MIN_PLAYERS players have 900+ league
    minutes, i.e. a season that is complete or far enough along for a fair comparison. Until the
    current season reaches that point, the list keeps using the previous season's performance.
  * Model: the step-4 gradient-boosting model, trained on every earlier season, predicts each
    player's relative fair value from that season's performance and context.
  * Market value: each player's latest Transfermarkt valuation (not the season-end value), so the
    gap moves as soon as the market re-prices a player.
  * Explanations: exact tree SHAP values from the equivalent LightGBM model (see step 5).

Writes dashboard/public/data/players.json, histories.json and scouting.json.
"""
import datetime as dt
import importlib
import json

import numpy as np
import pandas as pd

from common import ROOT, connect

valuation = importlib.import_module("04_undervalued")
robust = importlib.import_module("05_robustness")

DEST = ROOT / "dashboard" / "public" / "data"
MIN_PLAYERS = 3000
# If the newest market value is older than this when the list is rebuilt, the upstream dataset is
# treated as paused and the dashboard says so instead of implying the list is current.
STALE_AFTER_DAYS = 45


def r(x, nd=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def pct(x):
    return (np.exp(x) - 1) * 100


def season_label(s):
    return f"{s}/{str(s + 1)[2:]}"


def latest_values(con):
    return con.execute("""
        SELECT player_id, market_value_in_eur AS latest_value, strftime(date, '%Y-%m-%d') AS value_date
        FROM player_valuations
        WHERE market_value_in_eur > 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY date DESC, market_value_in_eur DESC) = 1
    """).df()


def build(con):
    df = valuation.load(con, require_value=False)
    counts = df.groupby("season").size()
    stats_season = int(counts[counts >= MIN_PLAYERS].index.max())

    train = df[(df["season"] < stats_season) & df["value"].notna()]
    score = (df[df["season"] == stats_season]
             .merge(latest_values(con), on="player_id", how="inner")
             .reset_index(drop=True))

    # Relative market value today, on the same scale as the model's target.
    log_latest = np.log(score["latest_value"])
    score["rel_actual"] = log_latest - log_latest.median()
    pred, _ = valuation.fit_predict(train, score)
    score["residual"] = score["rel_actual"] - pred
    score["model_value"] = score["latest_value"] * np.exp(-score["residual"])
    _, shap_values = robust.lgbm_shap(train, score)

    rows = []
    for idx, p in score.iterrows():
        contrib = shap_values.loc[idx].sort_values(key=np.abs, ascending=False).head(6)
        now = p["current_club_name"] if isinstance(p["current_club_name"], str) else None
        rows.append({
            "id": int(p["player_id"]), "name": p["name"], "age": int(p["age"]),
            "pos": p["position"], "sub": None if p["sub_position"] == "unknown" else p["sub_position"],
            "club": p["club_name"], "now": now if now and now != p["club_name"] else None,
            "league": p["league"],
            "min": int(p["league_minutes"]), "apps": int(p["league_apps"]),
            "g": int(p["goals"]), "a": int(p["assists"]), "ga90": r(p["ga90"], 2),
            "euroMin": int(p["euro_minutes"]),
            "value": int(p["latest_value"]), "valueDate": p["value_date"],
            "model": int(round(p["model_value"], -4)),
            "gap": r(pct(-p["residual"]), 1),
            "contract": None if pd.isna(p["contract_expiration_date"]) else str(p["contract_expiration_date"])[:10],
            "excluded": p["league"] in valuation.EXCLUDE_FROM_LIST,
            "shap": [[f, r(pct(v), 1)] for f, v in contrib.items()],
        })

    ids = [p["id"] for p in rows]
    hist = con.execute("""
        SELECT player_id, strftime(date, '%Y-%m-%d') AS d, market_value_in_eur AS v
        FROM player_valuations
        WHERE player_id IN (SELECT UNNEST(?)) AND market_value_in_eur > 0
        ORDER BY player_id, date, market_value_in_eur
    """, [ids]).df()
    histories = {str(pid): [[d, int(v)] for d, v in zip(g["d"], g["v"])] for pid, g in hist.groupby("player_id")}

    values_as_of = max(p["valueDate"] for p in rows)
    today = dt.datetime.now(dt.timezone.utc).date()
    info = {
        "statsSeason": season_label(stats_season),
        "valuesAsOf": values_as_of,
        "refreshed": today.isoformat(),
        "stale": (today - dt.date.fromisoformat(values_as_of)).days > STALE_AFTER_DAYS,
        "players": len(rows),
        "trainSeasons": f"{season_label(int(train['season'].min()))}–{season_label(stats_season - 1)}",
    }
    return rows, histories, info


def main():
    con = connect()
    DEST.mkdir(parents=True, exist_ok=True)
    rows, histories, info = build(con)
    for name, obj in [("players", rows), ("histories", histories), ("scouting", info)]:
        path = DEST / f"{name}.json"
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1e6:.2f} MB")
    print(info)
    top = sorted((p for p in rows if p["age"] <= 26 and p["min"] >= 1500 and p["value"] >= 1e6 and not p["excluded"]),
                 key=lambda p: -p["gap"])[:5]
    print("Top undervalued:", ", ".join(f"{p['name']} ({p['gap']:+.0f}%)" for p in top))


if __name__ == "__main__":
    main()
