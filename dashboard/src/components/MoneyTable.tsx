import { useMemo, useState } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { Meta } from "../data";
import { eur } from "../data";
import type { Palette } from "../theme";
import { ChartCard, Legend } from "./ChartCard";

export type MoneyHistory = {
  model: {
    slope: number;
    intercepts: Record<string, number>;
    r2: number;
    r2OutOfSample: number;
    rankCorr: number;
    n: number;
    seasons: string;
  };
  minPlayers: number;
  rows: {
    league: string;
    season: number;
    club: string;
    id: number;
    played: number;
    points: number;
    gd: number;
    value: number;
    players: number;
    complete: boolean;
    expPoints: number | null;
    diff: number | null;
  }[];
};

export type MoneyLive = {
  fetched: string;
  valuesAsOf: string;
  leagues: Record<
    string,
    {
      season: number | null;
      matchday: number | null;
      rows: {
        pos: number;
        team: string;
        crest: string | null;
        played: number;
        points: number;
        gd: number;
        form: string | null;
        clubId: number | null;
        club: string | null;
        value: number | null;
        players: number;
        complete: boolean;
        expPoints: number | null;
        diff: number | null;
      }[];
    }
  >;
};

type Row = {
  pos: number;
  club: string;
  played: number;
  points: number;
  gd: number;
  value: number | null;
  players: number;
  complete: boolean;
  expPoints: number | null;
  diff: number | null;
  form?: string | null;
};

const LEAGUES = ["GB1", "ES1", "IT1", "L1", "FR1"];
const LIVE = "live";
const label = (s: number) => `${s}/${String(s + 1).slice(2)}`;
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}`;

export function MoneyTable({
  history,
  live,
  meta,
  palette,
}: {
  history: MoneyHistory;
  live: MoneyLive | null;
  meta: Meta;
  palette: Palette;
}) {
  const seasons = useMemo(() => [...new Set(history.rows.map((r) => r.season))].sort((a, b) => b - a), [history]);
  const liveLeague = (lg: string) => live?.leagues[lg];
  const [league, setLeague] = useState("GB1");
  const [season, setSeason] = useState<string>(live ? LIVE : String(seasons[0]));
  const [sortByDiff, setSortByDiff] = useState(false);
  const m = history.model;

  const isLive = season === LIVE && !!liveLeague(league);
  const rows: Row[] = useMemo(() => {
    if (isLive) {
      return liveLeague(league)!.rows.map((r) => ({
        pos: r.pos,
        club: r.team,
        played: r.played,
        points: r.points,
        gd: r.gd,
        value: r.value,
        players: r.players,
        complete: r.complete,
        expPoints: r.expPoints,
        diff: r.diff,
        form: r.form,
      }));
    }
    return history.rows
      .filter((r) => r.league === league && String(r.season) === season)
      .map((r, i) => ({ ...r, pos: i + 1 }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history, live, league, season, isLive]);

  const complete = rows.filter((r) => r.complete && r.value && r.played > 0);
  const meanLog = complete.reduce((s, r) => s + Math.log(r.value!), 0) / Math.max(1, complete.length);
  const expPpg = (v: number) => m.intercepts[league] + m.slope * (Math.log(v) - meanLog);
  const points = complete.map((r) => ({
    x: r.value! / 1e6,
    y: r.points / r.played,
    club: r.club,
    diff: r.diff ?? 0,
    exp: r.expPoints,
    pts: r.points,
  }));
  const xs = points.map((p) => p.x);
  // Padded log domain with round tick values, so edge dots are not clipped.
  const xMin = xs.length ? Math.min(...xs) * 0.8 : 10;
  const xMax = xs.length ? Math.max(...xs) * 1.25 : 1000;
  const xTicks = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000].filter((t) => t >= xMin && t <= xMax);
  const line =
    xs.length > 1
      ? [Math.min(...xs), Math.max(...xs)].map((x) => ({ x, y: expPpg(x * 1e6) }))
      : [];
  const over = points.filter((p) => p.diff >= 3);
  const under = points.filter((p) => p.diff <= -3);
  const near = points.filter((p) => Math.abs(p.diff) < 3);

  const tableRows = sortByDiff ? [...rows].sort((a, b) => (b.diff ?? -999) - (a.diff ?? -999)) : rows;
  const allTime = history.rows.filter((r) => r.complete && r.diff != null);
  const best = [...allTime].sort((a, b) => b.diff! - a.diff!).slice(0, 8);
  const worst = [...allTime].sort((a, b) => a.diff! - b.diff!).slice(0, 8);
  const jump = (lg: string, s: number) => {
    setLeague(lg);
    setSeason(String(s));
    document.getElementById("money-controls")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const lgName = (lg: string) => meta.leagues[lg] ?? lg;
  const ll = liveLeague(league);

  return (
    <>
      <h1>Money vs. the table</h1>
      <p className="lede">
        How far does a club's preseason squad value go in explaining where it finishes? Points expected from squad value
        are compared with points actually won, for every big-five season since 2018/19
        {live ? " and live for the current season" : ""}.
      </p>
      <div className="tiles tiles-3">
        <div className="card tile static">
          <span className="tile-value">{Math.round(m.r2OutOfSample * 100)}%</span>
          <span className="tile-label">
            of the variation in points per game is explained by preseason squad value (out-of-sample, {m.seasons}).
          </span>
        </div>
        <div className="card tile static">
          <span className="tile-value">+{Math.round(m.slope * Math.log(2) * 38)} pts</span>
          <span className="tile-label">over a 38-game season for doubling squad value relative to the league average.</span>
        </div>
        <div className="card tile static">
          <span className="tile-value">{m.rankCorr.toFixed(2)}</span>
          <span className="tile-label">average rank correlation between squad value and final points within a season.</span>
        </div>
      </div>

      <div className="filters" id="money-controls" style={{ marginTop: 24 }}>
        <div className="seg" role="group" aria-label="League">
          {LEAGUES.map((lg) => (
            <button key={lg} aria-pressed={league === lg} onClick={() => setLeague(lg)}>
              {lgName(lg)}
            </button>
          ))}
        </div>
        <label className="field">
          Season
          <select value={season} onChange={(e) => setSeason(e.target.value)}>
            {live && <option value={LIVE}>Live {ll?.season ? label(ll.season) : ""}</option>}
            {seasons.map((s) => (
              <option key={s} value={String(s)}>
                {label(s)}
              </option>
            ))}
          </select>
        </label>
        {isLive && ll && (
          <span className="refresh-note" style={{ margin: 0 }}>
            <span className="refresh-dot" aria-hidden="true" />
            Live · matchday {ll.matchday ?? "–"} · standings updated {live!.fetched.replace("T", " ").replace("Z", " UTC")}
          </span>
        )}
      </div>

      <div className="grid-2">
        <ChartCard
          title={`${lgName(league)} ${isLive ? "(live)" : label(Number(season))}: squad value vs. points per game`}
          subtitle={`Line = points per game expected from squad value · preseason values ${
            isLive ? `as of ${live!.valuesAsOf}` : "on 31 August"
          }`}
        >
          <div style={{ height: 320 }}>
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 10, right: 16, bottom: 18, left: 0 }}>
                <CartesianGrid stroke={palette.grid} />
                <XAxis
                  type="number"
                  dataKey="x"
                  scale="log"
                  domain={[xMin, xMax]}
                  ticks={xTicks}
                  tickFormatter={(v) => `€${v >= 1000 ? `${(v / 1000).toFixed(1)}bn` : `${Math.round(v)}m`}`}
                  tickLine={false}
                  axisLine={{ stroke: palette.axis }}
                  label={{ value: "Preseason squad value (log scale)", position: "insideBottom", offset: -10, fontSize: 11 }}
                />
                <YAxis type="number" dataKey="y" tickLine={false} axisLine={false} width={40} domain={[0, "auto"]} />
                <Tooltip
                  cursor={false}
                  content={({ active, payload }) => {
                    const p = (payload?.[0]?.payload ?? null) as (typeof points)[number] | null;
                    if (!active || !p || !p.club) return null;
                    return (
                      <div className="tt">
                        <div className="tt-title">{p.club}</div>
                        <div className="tt-row">
                          <span className="lbl">Squad value</span>
                          <b>{eur(p.x * 1e6)}</b>
                        </div>
                        <div className="tt-row">
                          <span className="lbl">Points</span>
                          <b>{p.pts}</b>
                        </div>
                        <div className="tt-row">
                          <span className="lbl">Expected</span>
                          <b>{p.exp?.toFixed(1)}</b>
                        </div>
                        <div className="tt-row">
                          <span className="lbl">vs. expected</span>
                          <b>{signed(p.diff)}</b>
                        </div>
                      </div>
                    );
                  }}
                />
                <Scatter data={line} line={{ stroke: palette.muted, strokeWidth: 1.5 }} shape={() => <g />} isAnimationActive={false} legendType="none" />
                <Scatter data={near} fill={palette.neutral} isAnimationActive={false} shape={(s: { cx?: number; cy?: number }) => <circle cx={s.cx} cy={s.cy} r={5} fill={palette.muted} stroke={palette.surface} strokeWidth={2} />} />
                <Scatter data={over} isAnimationActive={false} shape={(s: { cx?: number; cy?: number }) => <circle cx={s.cx} cy={s.cy} r={5.5} fill={palette.pos} stroke={palette.surface} strokeWidth={2} />} />
                <Scatter data={under} isAnimationActive={false} shape={(s: { cx?: number; cy?: number }) => <circle cx={s.cx} cy={s.cy} r={5.5} fill={palette.neg} stroke={palette.surface} strokeWidth={2} />} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <Legend
            items={[
              { label: "3+ points above expectation", color: palette.pos, shape: "box" },
              { label: "within 3 points", color: palette.muted, shape: "box" },
              { label: "3+ points below", color: palette.neg, shape: "box" },
            ]}
          />
        </ChartCard>

        <section className="card">
          <div className="card-head">
            <div>
              <h3>Table</h3>
              <div className="card-sub">Expected points from preseason squad value; +/− = actual minus expected</div>
            </div>
            <button className="link-btn" onClick={() => setSortByDiff((s) => !s)}>
              {sortByDiff ? "Sort by position" : "Sort by +/−"}
            </button>
          </div>
          <div className="table-wrap" style={{ maxHeight: 420, overflow: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Club</th>
                  <th className="num">P</th>
                  <th className="num">Pts</th>
                  <th className="num">Exp</th>
                  <th className="num">+/−</th>
                  <th className="num hide-sm">Squad value</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((r) => (
                  <tr key={r.club} style={{ cursor: "default" }}>
                    <td className="num">{r.pos}</td>
                    <td className="player-td">{r.club}</td>
                    <td className="num">{r.played}</td>
                    <td className="num">
                      <b>{r.points}</b>
                    </td>
                    <td className="num">{r.expPoints == null ? "–" : r.expPoints.toFixed(1)}</td>
                    <td className={`num ${r.diff == null ? "" : r.diff >= 0 ? "gap-pos" : "gap-neg"}`}>
                      {r.diff == null ? "–" : signed(r.diff)}
                    </td>
                    <td className="num hide-sm">
                      {r.value ? eur(r.value) : "–"}
                      {r.value != null && !r.complete && <span className="tag" title={`Only ${r.players} valued players in the data`}>partial</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">
            "partial" = fewer than {history.minPlayers} valued players in the data (often newly promoted clubs), so no
            expectation is given.
          </p>
        </section>
      </div>

      <h2>Biggest over- and underperformers since 2018/19</h2>
      <p className="section-lede">Points won minus points expected from preseason squad value. Click a row to open that season.</p>
      <div className="grid-2">
        {[
          { title: "Did more with less", rows: best },
          { title: "Did less with more", rows: worst },
        ].map((block) => (
          <section className="card" key={block.title}>
            <h3 style={{ marginBottom: 10 }}>{block.title}</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Club</th>
                    <th>Season</th>
                    <th className="num">Pts</th>
                    <th className="num">Exp</th>
                    <th className="num">+/−</th>
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((r) => (
                    <tr key={`${r.id}-${r.season}`} tabIndex={0} onClick={() => jump(r.league, r.season)} onKeyDown={(e) => e.key === "Enter" && jump(r.league, r.season)}>
                      <td className="player-td">
                        <div className="player-cell">
                          <span>{r.club}</span>
                          <span className="club">{lgName(r.league)}</span>
                        </div>
                      </td>
                      <td>{label(r.season)}</td>
                      <td className="num">{r.points}</td>
                      <td className="num">{r.expPoints?.toFixed(0)}</td>
                      <td className={`num ${r.diff! >= 0 ? "gap-pos" : "gap-neg"}`}>{signed(r.diff!)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
