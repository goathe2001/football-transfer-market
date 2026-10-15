"""Step 5: robustness and interpretability checks for steps 2-4.

A. Quantile regression (step 2). OLS describes the average deal. Is the Premier League premium the
   same for cheap and expensive outcomes, or driven by a few blockbuster overpays? Re-estimate the
   premium model at the 10th, 25th, 50th, 75th and 90th percentiles of the premium distribution.

B. Placebo / randomization inference (step 3). Shuffle the "scored or assisted" label among players
   inside the same matching cell 1,000 times and re-estimate the effect each time. If the real effect
   comes from goals and assists rather than from how the comparison is built, the shuffled effects
   should centre on zero and the real one should sit far outside them.

C. SHAP explanations (step 4). Which features drive the valuation model overall, and why does it
   rate a specific undervalued player above his market value?

Outputs
  outputs/05_quantile_regression.csv, outputs/05_placebo.csv, outputs/05_shap_importance.csv,
  outputs/05_shap_examples.csv, figures/05_robustness.png
"""
import importlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import FIG_DIR, OUT_DIR, connect

premium = importlib.import_module("02_transfer_premium")
tournament = importlib.import_module("03_world_cup_effect")
valuation = importlib.import_module("04_undervalued")

RNG = np.random.default_rng(42)
N_PERM = 1000
QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]
FEATURE_LABELS = {
    "league_minutes": "League minutes", "minute_share": "Share of club minutes", "age": "Age",
    "league": "League", "club_ppg": "Club points per game", "club_gd": "Club goal difference",
    "euro_minutes": "European minutes", "ga90": "Goals + assists per 90", "g90": "Goals per 90",
    "a90": "Assists per 90", "position": "Position", "sub_position": "Detailed position",
    "league_apps": "League appearances", "height_in_cm": "Height", "euro_ga90": "European G+A per 90",
    "yellows90": "Yellow cards per 90", "foot": "Preferred foot",
}


def pct(x):
    return (np.exp(x) - 1) * 100


# --------------------------------------------------------------------------- A. quantile regression
def quantile_regression(con):
    df = premium.load(con).assign(log_mv=lambda d: np.log(d["market_value"]),
                                  deadline_week=lambda d: d["deadline_week"].astype(int),
                                  winter_window=lambda d: d["winter_window"].astype(int))
    formula = ("log_premium ~ C(buy_group, Treatment('Other')) + C(sell_group, Treatment('Other'))"
               " + C(age_band, Treatment('24-26')) + C(position, Treatment('Midfield'))"
               " + log_mv + deadline_week + winter_window + C(season_start)")
    terms = {"C(buy_group, Treatment('Other'))[T.GB1]": "Premier League buyer",
             "C(buy_group, Treatment('Other'))[T.IT1]": "Serie A buyer",
             "C(age_band, Treatment('24-26'))[T.U21]": "Under-21 player"}
    rows = []
    for q in QUANTILES:
        m = smf.quantreg(formula, df).fit(q=q, max_iter=5000)
        ci = m.conf_int()
        for t, label in terms.items():
            rows.append({"quantile": q, "term": label, "effect": m.params[t],
                         "lo": ci.loc[t, 0], "hi": ci.loc[t, 1]})
    ols = smf.ols(formula, df).fit()
    for t, label in terms.items():
        rows.append({"quantile": "OLS", "term": label, "effect": ols.params[t],
                     "lo": np.nan, "hi": np.nan})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------- B. placebo test
def within_cell_effect(y, t, cell_codes):
    """OLS coefficient on t with cell fixed effects (Frisch-Waugh: demean both within cell)."""
    def demean(v):
        means = np.bincount(cell_codes, weights=v) / np.bincount(cell_codes)
        return v - means[cell_codes]
    dy, dt = demean(y), demean(t)
    return (dt * dy).sum() / (dt * dt).sum()


def permute_within(t, cell_codes):
    out = t.copy()
    order = np.argsort(cell_codes, kind="stable")
    bounds = np.flatnonzero(np.diff(cell_codes[order])) + 1
    for idx in np.split(order, bounds):
        out[idx] = RNG.permutation(t[idx])
    return out


def placebo(con):
    pq = tournament.per_player_quarter(tournament.load(con))
    rows, draws = [], {}
    for qtr in (2, 4):
        d = pq[pq["quarter"] == qtr]
        d = d[d.groupby("cell_mom")["treated"].transform(lambda s: 0 < s.mean() < 1)]
        y = d["log_change"].to_numpy()
        t = d["treated"].to_numpy().astype(float)
        cells = d["cell_mom"].astype("category").cat.codes.to_numpy()
        real = within_cell_effect(y, t, cells)
        null = np.array([within_cell_effect(y, permute_within(t, cells), cells) for _ in range(N_PERM)])
        p = (np.sum(np.abs(null) >= abs(real)) + 1) / (N_PERM + 1)
        rows.append({"quarter": qtr, "real_effect_pct": pct(real),
                     "placebo_mean_pct": pct(null.mean()), "placebo_p95_pct": pct(np.quantile(null, 0.95)),
                     "placebo_max_pct": pct(null.max()), "permutation_p": p})
        draws[qtr] = (real, null)
    return pd.DataFrame(rows), draws


# ---------------------------------------------------------------------------------- C. SHAP
def lgbm_shap(train, test):
    """Fit LightGBM on the step-4 features and return (predictions, exact tree SHAP values) for test."""
    import lightgbm as lgb

    cats = {c: sorted(train[c].unique()) for c in valuation.CATS}
    X_train, X_test = valuation.design(train, cats), valuation.design(test, cats)
    lgbm = lgb.LGBMRegressor(n_estimators=600, learning_rate=0.05, num_leaves=31, min_child_samples=40,
                             reg_lambda=1.0, subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
                             random_state=0, verbose=-1)
    lgbm.fit(X_train, train["rel_value"], categorical_feature=valuation.CATS)
    contrib = lgbm.predict(X_test, pred_contrib=True)  # last column = baseline
    values = pd.DataFrame(contrib[:, :-1], columns=X_test.columns, index=X_test.index)
    return lgbm.predict(X_test), values


def fit_shap(con):
    """Exact tree SHAP values via LightGBM for every 2025/26 player-season.

    The step-4 model (scikit-learn HistGradientBoosting) has no fast exact SHAP implementation for
    native categorical features, so the same features are refit with LightGBM, which computes tree
    SHAP values natively. Its accuracy and residuals are checked against the step-4 model before use.

    Returns (test frame with step-4 and LightGBM residuals, SHAP values in log points, check dict).
    """
    from sklearn.metrics import r2_score

    df = valuation.load(con)
    train, test = df[df["season"] < valuation.CURRENT], df[df["season"] == valuation.CURRENT].copy()
    lgb_pred, values = lgbm_shap(train, test)

    # Agreement with the step-4 model.
    hgb_pred, _ = valuation.fit_predict(train, test)
    check = {"r2_lightgbm": r2_score(test["rel_value"], lgb_pred),
             "r2_step4_model": r2_score(test["rel_value"], hgb_pred),
             "residual_correlation": np.corrcoef(test["rel_value"] - lgb_pred,
                                                 test["rel_value"] - hgb_pred)[0, 1]}

    test["residual_step4"] = test["rel_value"] - hgb_pred
    test["residual_lgbm"] = test["rel_value"] - lgb_pred
    return test, values, check


def shap_analysis(con):
    test, values, check = fit_shap(con)
    importance =(values.abs().mean().sort_values(ascending=False)
                  .rename("mean_abs_shap").reset_index().rename(columns={"index": "feature"}))
    importance["label"] = importance["feature"].map(FEATURE_LABELS)
    # Mean |SHAP| in log points -> approximate typical % swing in predicted value.
    importance["typical_swing_pct"] = pct(importance["mean_abs_shap"])

    # Explain the top of the step-4 scouting list.
    pick =test[(test["league_minutes"] >= 1500) & (test["age"] <= 26) & (test["value"] >= 1e6)
                & ~test["league"].isin(valuation.EXCLUDE_FROM_LIST)].nsmallest(3, "residual_step4")
    examples = []
    for idx, r in pick.iterrows():
        top = values.loc[idx].sort_values(key=np.abs, ascending=False).head(5)
        for feat, v in top.items():
            examples.append({"player": r["name"], "club": r["club_name"], "value_m": r["value"] / 1e6,
                             "model_value_m": r["value"] * np.exp(-r["residual_lgbm"]) / 1e6,
                             "feature": FEATURE_LABELS[feat], "feature_value": test.loc[idx, feat],
                             "shap_pct": pct(v)})
    return importance, pd.DataFrame(examples), check


# ----------------------------------------------------------------------------------- plotting
def plot(qr, draws, importance, examples):
    FIG_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.3), gridspec_kw={"width_ratios": [1, 1, 1.15]})

    a = axes[0]
    colors = {"Premier League buyer": "#7b2cbf", "Serie A buyer": "#2a6fdb", "Under-21 player": "#e07b39"}
    for term, d in qr[qr["quantile"] != "OLS"].groupby("term"):
        q = d["quantile"].astype(float)
        a.fill_between(q, pct(d["lo"]), pct(d["hi"]), color=colors[term], alpha=0.12)
        a.plot(q, pct(d["effect"]), "o-", color=colors[term], lw=2, label=term)
        ols = qr[(qr["quantile"] == "OLS") & (qr["term"] == term)]["effect"].iloc[0]
        a.axhline(pct(ols), color=colors[term], ls=":", lw=1)
    a.axhline(0, color="#444", lw=0.8)
    a.set_xticks(QUANTILES, [f"{int(q * 100)}th" for q in QUANTILES])
    a.set(title="A. Quantile regression of transfer premium\n(dotted = OLS average)",
          xlabel="Percentile of fee / market value", ylabel="Effect on fee vs. market value (%)")
    a.legend(frameon=False, fontsize=9)

    a = axes[1]
    for qtr, color in [(2, "#9bbcf0"), (4, "#2a6fdb")]:
        real, null = draws[qtr]
        a.hist(pct(null), bins=40, color=color, alpha=0.6,
               label=f"Shuffled labels, {qtr * 3} months after")
        a.axvline(pct(real), color=color, lw=2.5)
        a.text(pct(real) - 0.3, a.get_ylim()[1] * (0.92 if qtr == 4 else 0.80),
               f"real, {qtr * 3} mo: +{pct(real):.1f}%", color=color, fontsize=9, fontweight="bold",
               ha="right")
    a.axvline(0, color="#444", lw=0.8)
    a.set(title=f"B. Placebo: {N_PERM:,} within-cell label shuffles\n(real effect = vertical line)",
          xlabel="Estimated tournament effect (%)", ylabel="Count")
    a.set_xlim(right=max(pct(r) for r, _ in draws.values()) + 1.5)
    a.legend(frameon=False, fontsize=9, loc="center left", bbox_to_anchor=(0.32, 0.45))

    a = axes[2]
    top = importance.head(10).iloc[::-1]
    a.barh(top["label"], top["typical_swing_pct"], color="#3a9e5f")
    a.set(title="C. SHAP: what drives the valuation model\n(mean |SHAP| over 2025/26 players)",
          xlabel="Typical effect on predicted value (%)")
    # Annotate the highest-valued of the explained players (the most recognisable example).
    first = examples.sort_values("value_m")["player"].iloc[-1]
    ex = examples[examples["player"] == first]
    note = (f"Why the model rates {first} at €{ex['model_value_m'].iloc[0]:.1f}m "
            f"vs. €{ex['value_m'].iloc[0]:.1f}m market:\n"
            + "\n".join(f"  {r.feature}: {r.shap_pct:+.0f}%" for r in ex.head(4).itertuples()))
    a.text(0.98, 0.04, note, transform=a.transAxes, ha="right", va="bottom", fontsize=8.5,
           bbox=dict(boxstyle="round", fc="white", ec="#bbb"))

    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    path = FIG_DIR / "05_robustness.png"
    fig.savefig(path, dpi=160)
    return path


def main():
    con = connect()
    OUT_DIR.mkdir(exist_ok=True)

    qr = quantile_regression(con)
    qr.assign(effect_pct=pct(qr["effect"])).to_csv(OUT_DIR / "05_quantile_regression.csv", index=False)
    print("A. Quantile regression (effect on fee vs. market value)")
    print(qr.assign(effect_pct=pct(qr["effect"]).round(1)).pivot(index="term", columns="quantile",
                                                                   values="effect_pct").to_string())

    pl, draws = placebo(con)
    pl.to_csv(OUT_DIR / "05_placebo.csv", index=False)
    print("\nB. Placebo (randomization inference)")
    print(pl.round(3).to_string(index=False))

    importance, examples, check = shap_analysis(con)
    print("\nC. SHAP model check (2025/26):", {k: round(v, 3) for k, v in check.items()})
    importance.to_csv(OUT_DIR / "05_shap_importance.csv", index=False)
    examples.to_csv(OUT_DIR / "05_shap_examples.csv", index=False)
    print("\nC. SHAP feature importance (typical % swing in predicted value)")
    print(importance.head(10)[["label", "typical_swing_pct"]].round(1).to_string(index=False))
    print("\nC. Why the top undervalued players are rated higher")
    print(examples.round(2).to_string(index=False))

    print(f"\nFigure: {plot(qr, draws, importance, examples)}")


if __name__ == "__main__":
    main()
