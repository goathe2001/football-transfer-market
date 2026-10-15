"""Step 6: export analysis results as compact JSON for the interactive dashboard.

Writes to dashboard/public/data/:
  players.json    every 2025/26 player-season in the valuation model (>= 900 league minutes): stats,
                  market value, model fair value, gap, and SHAP contributions
  histories.json  full market-value history for those players, keyed by player_id
  insights.json   age curves, transfer premiums, tournament event study, backtest, robustness
  meta.json       league names, feature labels, headline numbers, data snapshot date

Run after steps 1-5 (it reads some of their CSV outputs).
"""
import importlib
import json

import numpy as np
import pandas as pd

from common import OUT_DIR, ROOT, connect

age = importlib.import_module("01_age_curves")
premium = importlib.import_module("02_transfer_premium")
valuation = importlib.import_module("04_undervalued")
robust = importlib.import_module("05_robustness")

DEST = ROOT / "dashboard" / "public" / "data"
LEAGUE_NAMES = {
    "GB1": "Premier League", "ES1": "LaLiga", "IT1": "Serie A", "L1": "Bundesliga", "FR1": "Ligue 1",
    "NL1": "Eredivisie", "PO1": "Liga Portugal", "BE1": "Belgian Pro League", "TR1": "Süper Lig",
    "SC1": "Scottish Premiership", "GR1": "Greek Super League", "DK1": "Danish Superliga",
    "RU1": "Russian Premier League", "UKR1": "Ukrainian Premier League", "Other": "Other leagues",
}


def r(x, nd=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def pct(x):
    return (np.exp(x) - 1) * 100


def players_and_histories(con):
    test, values, check = robust.fit_shap(con)
    test = test.assign(model_value=lambda d: d["value"] * np.exp(-d["residual_step4"]))
    rows = []
    for idx, p in test.iterrows():
        contrib = values.loc[idx].sort_values(key=np.abs, ascending=False)
        rows.append({
            "id": int(p["player_id"]), "name": p["name"], "age": int(p["age"]),
            "pos": p["position"], "sub": None if p["sub_position"] == "unknown" else p["sub_position"],
            "club": p["club_name"], "league": p["league"],
            "min": int(p["league_minutes"]), "apps": int(p["league_apps"]),
            "g": int(p["goals"]), "a": int(p["assists"]), "ga90": r(p["ga90"], 2),
            "euroMin": int(p["euro_minutes"]),
            "value": int(p["value"]), "model": int(round(p["model_value"], -4)),
            "gap": r(pct(-p["residual_step4"]), 1),
            "contract": None if pd.isna(p["contract_expiration_date"]) else str(p["contract_expiration_date"])[:10],
            "excluded": p["league"] in valuation.EXCLUDE_FROM_LIST,
            "shap": [[f, r(pct(v), 1)] for f, v in contrib.head(6).items()],
        })
    ids = [p["id"] for p in rows]
    hist = con.execute("""
        SELECT player_id, strftime(date, '%Y-%m-%d') AS d, market_value_in_eur AS v
        FROM player_valuations
        WHERE player_id IN (SELECT UNNEST(?)) AND market_value_in_eur > 0
        ORDER BY player_id, date, market_value_in_eur
    """, [ids]).df()
    histories = {str(pid): [[d, int(v)] for d, v in zip(g["d"], g["v"])]
                 for pid, g in hist.groupby("player_id")}
    return rows, histories, check


def insights(con):
    out = {}

    # 1. Age curves: naive cross-section vs. within-player (delta method), all leagues.
    df = age.load_player_age_values(con, big5=False)
    cs = age.cross_sectional(df)
    _, curves = age.delta_method(df)
    out["ageCurves"] = {}
    for c in curves:
        pos = c["position"]
        naive = cs[cs["position"] == pos].set_index("age")["median"]
        naive = naive / naive.max()
        delta = dict(zip(c["ages"].tolist(), c["relative_value"].tolist()))
        out["ageCurves"][pos] = {
            "peak": c["peak_age"],
            "points": [{"age": int(a), "delta": r(delta.get(a)), "naive": r(naive.get(a))}
                       for a in range(age.MIN_AGE, age.MAX_AGE + 1)],
        }

    # 2. Transfer premiums: trend by buying league, regression effects, quantile regression.
    t = premium.load(con)
    done = t[t["season_start"] < t["season_start"].max()]
    trend = (done.groupby(["buy_group", "season_start"])["log_premium"].median().unstack(0)
             .sort_index().rolling(3, min_periods=2).median())
    trend = trend.dropna(how="all")
    out["premiumTrend"] = [{"season": int(s), **{lg: r(pct(trend.loc[s, lg]), 1) for lg in trend.columns}}
                           for s in trend.index]
    reg = pd.read_csv(OUT_DIR / "02_regression.csv")
    keep = reg[reg["term"].str.contains("buy_group|age_band|deadline|winter")]
    out["premiumEffects"] = [{"term": tm, "effect": r(e, 1), "lo": r(pct(lo), 1), "hi": r(pct(hi), 1)}
                             for tm, e, lo, hi in zip(keep["term"], keep["effect_pct"],
                                                      keep["[0.025"], keep["0.975]"])]
    q = pd.read_csv(OUT_DIR / "05_quantile_regression.csv")
    out["quantile"] = [{"quantile": qq, "term": tm, "effect": r(e, 1),
                        "lo": r(pct(lo), 1) if pd.notna(lo) else None,
                        "hi": r(pct(hi), 1) if pd.notna(hi) else None}
                       for qq, tm, e, lo, hi in zip(q["quantile"], q["term"], q["effect_pct"], q["lo"], q["hi"])]

    # 3. Tournament effect.
    es = pd.read_csv(OUT_DIR / "03_event_study.csv")
    out["eventStudy"] = [{"quarter": int(x.quarter), "spec": x.spec, "effect": r(x.effect_pct, 1),
                          "lo": r(pct(x.lo), 1), "hi": r(pct(x.hi), 1),
                          "treated": int(x.n_treated), "control": int(x.n_control)}
                         for x in es.itertuples()]
    dr = pd.read_csv(OUT_DIR / "03_dose_response.csv")
    out["dose"] = [{"quarter": int(x.quarter), "contrib": str(x.contributions), "effect": r(x.effect_pct, 1),
                    "lo": r(pct(x.lo), 1), "hi": r(pct(x.hi), 1), "n": int(x.n)} for x in dr.itertuples()]
    pl = pd.read_csv(OUT_DIR / "05_placebo.csv")
    out["placebo"] = [{k: r(v, 4) for k, v in row.items()} for row in pl.to_dict("records")]

    # 4. Valuation model: backtest deciles, walk-forward accuracy, SHAP importance.
    dec = pd.read_csv(OUT_DIR / "04_backtest_deciles.csv")
    out["deciles"] = [{"decile": int(x.decile), "growth": r(pct(x.mean), 1),
                       "lo": r(pct(x.mean - 1.96 * x.sem), 1), "hi": r(pct(x.mean + 1.96 * x.sem), 1),
                       "n": int(x.n)} for x in dec.itertuples()]
    met = pd.read_csv(OUT_DIR / "04_model_metrics.csv")
    out["metrics"] = [{"season": x.season, "r2": r(x.r2_gbm), "r2Linear": r(x.r2_linear),
                       "medianErr": r(x.median_abs_err_pct, 1)} for x in met.itertuples()]
    imp = pd.read_csv(OUT_DIR / "05_shap_importance.csv")
    out["shapImportance"] = [{"feature": f, "swing": r(s, 1)} for f, s in zip(imp["feature"], imp["typical_swing_pct"])]
    return out


def main():
    con = connect()
    DEST.mkdir(parents=True, exist_ok=True)
    players, histories, check = players_and_histories(con)
    ins = insights(con)

    snapshot = con.execute("SELECT strftime(MAX(date), '%Y-%m-%d') FROM player_valuations").fetchone()[0]
    leagues = sorted({p["league"] for p in players})
    comp = dict(con.execute("SELECT competition_id, name FROM competitions").fetchall())
    league_names = {lg: LEAGUE_NAMES.get(lg, comp.get(lg, lg).replace("-", " ").title()) for lg in leagues}
    league_names["Other"] = LEAGUE_NAMES["Other"]
    meta = {
        "snapshot": snapshot,
        "season": "2025/26",
        "leagues": league_names,
        "features": robust.FEATURE_LABELS,
        "excludedLeagues": sorted(valuation.EXCLUDE_FROM_LIST),
        "shapCheck": {k: r(v) for k, v in check.items()},
        "counts": {"transfers": 175165, "valuations": 656301, "appearances": 1894350,
                   "paidTransfers": 15983, "playerSeasons": 50113, "tournaments": 7},
    }

    for name, obj in [("players", players), ("histories", histories), ("insights", ins), ("meta", meta)]:
        path = DEST / f"{name}.json"
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1e6:.2f} MB")
    print(f"{len(players):,} players, {sum(len(h) for h in histories.values()):,} valuation points")


if __name__ == "__main__":
    main()
