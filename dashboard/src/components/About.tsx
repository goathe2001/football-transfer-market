import type { Meta } from "../data";

export function About({ meta }: { meta: Meta }) {
  return (
    <>
      <h1>Method &amp; data</h1>
      <p className="lede">
        Every number on this site comes from scripts in the{" "}
        <a href="https://github.com/goathe2001/football-transfer-market">GitHub repository</a>, which runs end to end from a
        public dataset and gives identical results on every run.
      </p>
      <div className="grid-2">
        <section className="card">
          <h3>Data</h3>
          <p className="card-sub">
            <a href="https://github.com/dcaribou/transfermarkt-datasets">transfermarkt-datasets</a>, a cleaned export of
            Transfermarkt refreshed weekly, queried with SQL in DuckDB. Snapshot: valuations through {meta.snapshot}.
          </p>
          <ul className="card-sub">
            <li>{meta.counts.transfers.toLocaleString()} transfers ({meta.counts.paidTransfers.toLocaleString()} paid, 2012/13 onward, used for premiums)</li>
            <li>{meta.counts.valuations.toLocaleString()} market valuations</li>
            <li>{meta.counts.appearances.toLocaleString()} match appearances</li>
            <li>{meta.counts.playerSeasons.toLocaleString()} player-seasons with at least 900 league minutes (valuation model)</li>
          </ul>
        </section>
        <section className="card">
          <h3>Methods</h3>
          <ul className="card-sub">
            <li><b>Transfer premiums:</b> OLS on log(fee ÷ market value) with season fixed effects and standard errors clustered by buying club; quantile regression for the distribution.</li>
            <li><b>Tournament effect:</b> event study with matching cells (tournament × position × age × value × pre-tournament momentum), checked with 1,000 within-cell placebo shuffles.</li>
            <li><b>Valuation model:</b> gradient boosting, walk-forward validation (each season predicted by a model trained on earlier seasons only), SHAP explanations.</li>
            <li><b>Age curves:</b> delta method (within-player changes) against the naive cross-section.</li>
          </ul>
        </section>
        <section className="card">
          <h3>Limitations</h3>
          <ul className="card-sub">
            <li>Transfermarkt market values are community estimates, not observed prices.</li>
            <li>Free transfers, loans and loan returns all carry a fee of 0, so premiums cover paid transfers only.</li>
            <li>Squads for past tournaments are not recorded; scorers and assisters are identified from goal events.</li>
            <li>The valuation model sees goals, assists, minutes and team context, not defensive quality, injuries or contracts.</li>
            <li>
              {meta.excludedLeagues.map((l) => meta.leagues[l] ?? l).join(" and ")} players are hidden from the scouting list by
              default: club values there have been structurally lower since 2022.
            </li>
          </ul>
        </section>
        <section className="card">
          <h3>Reading the scouting list</h3>
          <p className="card-sub">
            Gap = model fair value ÷ market value − 1. A large positive gap means the player's market value is low for his
            minutes, output, team and league. In the backtest, the most undervalued tenth of players gained about 16%
            relative to the market over the following season. A high gap is a reason to look closer, not a valuation.
          </p>
        </section>
      </div>
    </>
  );
}
