import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Meta } from "../data";
import type { Palette } from "../theme";
import { ChartCard, Legend } from "./ChartCard";
import { RoundedBar, TooltipBox } from "./chartParts";

export type MatchModel = {
  model: string;
  train: string;
  test: string;
  testMatches: number;
  skill: number;
  summary: { model: string; rps_test: number; rps_test_early: number; rps_test_rest: number; accuracy_test: number }[];
  perSeason: { season: number; model: number; base: number }[];
  calibration: { outcome: "home" | "draw" | "away"; predicted: number; observed: number; n: number }[];
  params: { K: number; H: number; reg: number; margin: boolean; w: number; b: number };
  homeWinRate: { before: number; since: number };
};

type Result = {
  date: string;
  md: number | null;
  home: string;
  away: string;
  hg: number;
  ag: number;
  p: [number, number, number];
  outcome: "H" | "D" | "A";
  rps: number;
  fav: boolean;
};

export type MatchPredictions = {
  fetched: string;
  overall: { played: number; rps: number | null; rpsBase: number | null; skill: number | null; favHit: number | null };
  leagues: Record<
    string,
    {
      played: number;
      rps: number | null;
      rpsBase: number | null;
      favHit: number | null;
      nextMatchday: number | null;
      next: { date: string; home: string; away: string; p: [number, number, number] }[];
      results: Result[];
      ratings: { team: string; rating: number; change: number }[];
    }
  >;
};

const LEAGUES = ["GB1", "ES1", "IT1", "L1", "FR1"];
const pct = (v: number) => `${Math.round(v * 100)}%`;
const label = (s: number) => `${s}/${String(s + 1).slice(2)}`;

function ProbBar({ p, colors }: { p: [number, number, number]; colors: [string, string, string] }) {
  const names = ["Home win", "Draw", "Away win"];
  return (
    <div className="probbar" role="img" aria-label={names.map((n, i) => `${n} ${pct(p[i])}`).join(", ")}>
      {p.map((v, i) => (
        <div key={i} className="probbar-seg" style={{ flexGrow: Math.max(v, 0.001), background: colors[i] }} title={`${names[i]}: ${pct(v)}`}>
          {v >= 0.14 && <span>{pct(v)}</span>}
        </div>
      ))}
    </div>
  );
}

export function Predictions({
  model,
  live,
  meta,
  palette,
}: {
  model: MatchModel;
  live: MatchPredictions | null;
  meta: Meta;
  palette: Palette;
}) {
  const [league, setLeague] = useState("GB1");
  const [showAll, setShowAll] = useState(false);
  const colors: [string, string, string] = [palette.series[0], palette.muted, palette.series[1]];
  const lg = live?.leagues[league];
  const elo = model.summary.find((s) => s.model === model.model)!;
  const base = model.summary.find((s) => s.model.startsWith("Baseline"))!;
  const eloOnly = model.summary.find((s) => s.model === "Elo");
  const lgName = (l: string) => meta.leagues[l] ?? l;

  const calib = ["home", "draw", "away"].map((o) => model.calibration.filter((c) => c.outcome === o));
  const calibRows = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85].map((x) => {
    const row: Record<string, number | null> = { x: Math.round(x * 100) };
    (["home", "draw", "away"] as const).forEach((o, i) => {
      const pt = calib[i].find((c) => Math.abs(c.predicted - x) < 0.05);
      row[o] = pt ? Math.round(pt.observed * 1000) / 10 : null;
    });
    row.ideal = Math.round(x * 100);
    return row;
  });
  const seasonRows = model.perSeason.map((r) => ({ ...r, label: label(r.season) }));
  const results = lg ? (showAll ? lg.results : lg.results.slice(0, 10)) : [];

  return (
    <>
      <h1>Match predictions</h1>
      <p className="lede">
        An Elo rating model with a squad-value prior gives each upcoming big-five match a probability of a home win, draw
        or away win. Every prediction uses only results known before kickoff, and the model's accuracy is tracked against
        a simple baseline. Forecasts only: nothing here is betting advice.
      </p>

      <div className="tiles tiles-3">
        <div className="card tile static">
          <span className="tile-value">{(model.skill * 100).toFixed(1)}%</span>
          <span className="tile-label">
            better than the baseline (ranked probability score) on {model.testMatches.toLocaleString()} test matches,{" "}
            {model.test}, never seen during fitting.
          </span>
        </div>
        <div className="card tile static">
          <span className="tile-value">{pct(elo.accuracy_test)}</span>
          <span className="tile-label">
            of test matches ended in the model's most likely outcome, vs. {pct(base.accuracy_test)} for always picking
            a home win.
          </span>
        </div>
        <div className="card tile static">
          {live && live.overall.played > 0 && live.overall.skill != null ? (
            <>
              <span className="tile-value">
                {live.overall.skill >= 0 ? "+" : "−"}
                {Math.abs(live.overall.skill * 100).toFixed(1)}%
              </span>
              <span className="tile-label">
                skill vs. baseline this season so far, over {live.overall.played} matches (favourite won{" "}
                {pct(live.overall.favHit ?? 0)}). Updated daily.
              </span>
            </>
          ) : (
            <>
              <span className="tile-value">–</span>
              <span className="tile-label">This season's live accuracy appears once the daily update has run.</span>
            </>
          )}
        </div>
      </div>

      <div className="filters" style={{ marginTop: 24 }}>
        <div className="seg" role="group" aria-label="League">
          {LEAGUES.map((l) => (
            <button key={l} aria-pressed={league === l} onClick={() => setLeague(l)}>
              {lgName(l)}
            </button>
          ))}
        </div>
        {live && (
          <span className="refresh-note" style={{ margin: 0 }}>
            <span className="refresh-dot" aria-hidden="true" />
            Results and fixtures updated {live.fetched.replace("T", " ").replace("Z", " UTC")}
          </span>
        )}
      </div>

      {lg ? (
        <>
          <div className="grid-2">
            <section className="card">
              <div className="card-head">
                <div>
                  <h3>
                    {lgName(league)} · next matchday {lg.nextMatchday ?? "–"}
                  </h3>
                  <div className="card-sub">Probability of home win, draw, away win</div>
                </div>
              </div>
              {lg.next.length === 0 ? (
                <div className="empty">No upcoming fixtures in the data.</div>
              ) : (
                <div className="fixtures">
                  {lg.next.map((f) => (
                    <div className="fixture" key={`${f.home}-${f.away}`}>
                      <div className="fixture-teams">
                        <span className="fixture-home">{f.home}</span>
                        <span className="muted small">
                          {new Date(f.date).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}
                        </span>
                        <span className="fixture-away">{f.away}</span>
                      </div>
                      <ProbBar p={f.p} colors={colors} />
                    </div>
                  ))}
                </div>
              )}
              <Legend
                items={[
                  { label: "Home win", color: colors[0], shape: "box" },
                  { label: "Draw", color: colors[1], shape: "box" },
                  { label: "Away win", color: colors[2], shape: "box" },
                ]}
              />
            </section>

            <section className="card">
              <div className="card-head">
                <div>
                  <h3>Power ratings</h3>
                  <div className="card-sub">Current Elo rating; change since the start of the season</div>
                </div>
              </div>
              <div className="table-wrap" style={{ maxHeight: 460, overflow: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th className="num">#</th>
                      <th>Team</th>
                      <th className="num">Rating</th>
                      <th className="num">Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lg.ratings.map((r, i) => (
                      <tr key={r.team} style={{ cursor: "default" }}>
                        <td className="num">{i + 1}</td>
                        <td>{r.team}</td>
                        <td className="num">{Math.round(r.rating)}</td>
                        <td className={`num ${r.change >= 0 ? "gap-pos" : "gap-neg"}`}>
                          {r.change >= 0 ? "+" : "−"}
                          {Math.abs(Math.round(r.change))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="card" style={{ marginTop: 16 }}>
            <div className="card-head">
              <div>
                <h3>Results vs. predictions</h3>
                <div className="card-sub">
                  {lg.played} matches this season · model RPS {lg.rps?.toFixed(3) ?? "–"} vs. baseline{" "}
                  {lg.rpsBase?.toFixed(3) ?? "–"} (lower is better) · favourite won {pct(lg.favHit ?? 0)}
                </div>
              </div>
              {lg.results.length > 10 && (
                <button className="link-btn" onClick={() => setShowAll((s) => !s)}>
                  {showAll ? "Show latest 10" : `Show all ${lg.results.length}`}
                </button>
              )}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th className="hide-sm">Date</th>
                    <th>Match</th>
                    <th className="num">Score</th>
                    <th style={{ minWidth: 150 }}>Pre-match probabilities</th>
                    <th className="num">Favourite</th>
                    <th className="num hide-sm">RPS</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={`${r.date}-${r.home}`} style={{ cursor: "default" }}>
                      <td className="hide-sm">{r.date.slice(5)}</td>
                      <td className="player-td">
                        {r.home} – {r.away}
                      </td>
                      <td className="num">
                        {r.hg}–{r.ag}
                      </td>
                      <td>
                        <ProbBar p={r.p} colors={colors} />
                      </td>
                      <td className={`num ${r.fav ? "gap-pos" : "gap-neg"}`} aria-label={r.fav ? "Favourite outcome happened" : "Favourite outcome missed"}>
                        {r.fav ? "✓ hit" : "✗ miss"}
                      </td>
                      <td className="num hide-sm">{r.rps.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <section className="card">
          <p className="card-sub">
            Live fixtures, results and ratings appear here once the daily update has run. The backtest below shows how the
            same model performed on the six seasons before this one.
          </p>
        </section>
      )}

      <h2>How well does the model work?</h2>
      <p className="section-lede">
        Parameters were tuned on {model.train} and the model was then scored on {model.test}. The ranked probability score
        (RPS) rewards putting high probability on what happened and penalises confident misses; lower is better.
        {eloOnly && ` Adding the squad-value prior lowers RPS only slightly (${eloOnly.rps_test.toFixed(4)} → ${elo.rps_test.toFixed(4)}).`}{" "}
        Home teams won {pct(model.homeWinRate.before)} of matches before 2020/21 and {pct(model.homeWinRate.since)} since, which is
        why the tuned model slightly over-predicts home wins on the test seasons.
      </p>
      <div className="grid-2">
        <ChartCard
          title="Calibration on test seasons"
          subtitle="When the model says X%, how often does it happen? Points on the diagonal are perfectly calibrated."
          rows={calibRows.filter((r) => r.home != null || r.draw != null || r.away != null)}
          columns={[
            { key: "x", label: "Predicted", num: true, fmt: (r) => `${r.x}%` },
            { key: "home", label: "Home win observed", num: true, fmt: (r) => (r.home == null ? "–" : `${r.home}%`) },
            { key: "draw", label: "Draw observed", num: true, fmt: (r) => (r.draw == null ? "–" : `${r.draw}%`) },
            { key: "away", label: "Away win observed", num: true, fmt: (r) => (r.away == null ? "–" : `${r.away}%`) },
          ]}
        >
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={calibRows} margin={{ top: 8, right: 12, bottom: 16, left: 0 }}>
                <CartesianGrid stroke={palette.grid} />
                <XAxis dataKey="x" type="number" domain={[0, 90]} ticks={[0, 20, 40, 60, 80]} tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={{ stroke: palette.axis }} label={{ value: "Predicted probability", position: "insideBottom", offset: -8, fontSize: 11 }} />
                <YAxis domain={[0, 90]} ticks={[0, 20, 40, 60, 80]} tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} />
                <Tooltip content={(p) => <TooltipBox {...(p as object)} title={(l) => `Predicted ${l}%`} fmt={(v) => `${v}% observed`} names={{ home: "Home win", draw: "Draw", away: "Away win", ideal: "Perfect calibration" }} />} />
                <Line dataKey="ideal" stroke={palette.axis} strokeWidth={1} dot={false} isAnimationActive={false} />
                <Line dataKey="home" stroke={colors[0]} strokeWidth={2} dot={{ r: 4, fill: colors[0], strokeWidth: 0 }} connectNulls isAnimationActive={false} />
                <Line dataKey="draw" stroke={colors[1]} strokeWidth={2} dot={{ r: 4, fill: colors[1], strokeWidth: 0 }} connectNulls isAnimationActive={false} />
                <Line dataKey="away" stroke={colors[2]} strokeWidth={2} dot={{ r: 4, fill: colors[2], strokeWidth: 0 }} connectNulls isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <Legend
            items={[
              { label: "Home win", color: colors[0] },
              { label: "Draw", color: colors[1] },
              { label: "Away win", color: colors[2] },
              { label: "Perfect calibration", color: palette.axis },
            ]}
          />
        </ChartCard>
        <ChartCard
          title="RPS by test season"
          subtitle="Model vs. a baseline that always predicts the historical outcome frequencies (lower is better)"
          rows={seasonRows}
          columns={[
            { key: "label", label: "Season" },
            { key: "model", label: "Model RPS", num: true, fmt: (r) => r.model.toFixed(4) },
            { key: "base", label: "Baseline RPS", num: true, fmt: (r) => r.base.toFixed(4) },
            { key: "skill", label: "Skill", num: true, fmt: (r) => `${((1 - r.model / r.base) * 100).toFixed(1)}%` },
          ]}
        >
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={seasonRows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={2}>
                <CartesianGrid vertical={false} stroke={palette.grid} />
                <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: palette.axis }} fontSize={11} />
                <YAxis tickLine={false} axisLine={false} width={44} domain={[0, 0.25]} ticks={[0, 0.05, 0.1, 0.15, 0.2, 0.25]} tickFormatter={(v) => v.toFixed(2)} />
                <Tooltip cursor={{ fill: palette.grid, opacity: 0.5 }} content={(p) => <TooltipBox {...(p as object)} fmt={(v) => v.toFixed(4)} names={{ base: "Baseline", model: model.model }} />} />
                <Bar dataKey="base" fill={palette.muted} maxBarSize={22} shape={(s: object) => <RoundedBar {...s} />} isAnimationActive={false} />
                <Bar dataKey="model" fill={colors[0]} maxBarSize={22} shape={(s: object) => <RoundedBar {...s} />} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <Legend
            items={[
              { label: "Baseline", color: palette.muted, shape: "box" },
              { label: model.model, color: colors[0], shape: "box" },
            ]}
          />
        </ChartCard>
      </div>
      <p className="note">
        Model: Elo ratings (K = {model.params.K}, margin-of-victory weighting {model.params.margin ? "on" : "off"}, home
        advantage {model.params.H} points, {model.params.reg === 0 ? "no" : `${model.params.reg * 100}%`} regression to the
        mean between seasons, squad-value prior weight {model.params.w}) turned into home/draw/away probabilities by an
        ordered logit. Promoted clubs start at the average rating of the clubs they replaced. Live predictions use the
        same ratings with the outcome model refitted on all seasons through 2025/26.
      </p>
    </>
  );
}
