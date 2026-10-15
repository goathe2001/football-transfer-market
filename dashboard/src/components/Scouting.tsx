import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Histories, Meta, Player, Scouting as ScoutingInfo } from "../data";
import { eur, signedPct, useJson } from "../data";
import type { Palette } from "../theme";
import { DivergingBars, TooltipBox } from "./chartParts";

type SortKey = "gap" | "value" | "model" | "age" | "min" | "ga90" | "name";

const POS_ABBR: Record<string, string> = {
  "Centre-Forward": "CF", "Second Striker": "SS", "Left Winger": "LW", "Right Winger": "RW",
  "Attacking Midfield": "AM", "Central Midfield": "CM", "Defensive Midfield": "DM",
  "Left Midfield": "LM", "Right Midfield": "RM", "Centre-Back": "CB", "Left-Back": "LB",
  "Right-Back": "RB", Goalkeeper: "GK", Attack: "FW", Midfield: "MF", Defender: "DF",
};
const SHORT_FEATURE: Record<string, string> = {
  minute_share: "Share of club mins", club_ppg: "Club points/game", club_gd: "Club goal diff.",
  euro_minutes: "European minutes", euro_ga90: "European G+A/90", ga90: "Goals+assists/90",
  sub_position: "Detailed position", league_minutes: "League minutes", league_apps: "Appearances",
  yellows90: "Yellow cards/90", height_in_cm: "Height",
};
const PAGE = 50;

export function Scouting({ players, meta, info, palette }: { players: Player[]; meta: Meta; info: ScoutingInfo; palette: Palette }) {
  const [q, setQ] = useState("");
  const [league, setLeague] = useState("all");
  const [pos, setPos] = useState("all");
  const [maxAge, setMaxAge] = useState(26);
  const [minMin, setMinMin] = useState(1500);
  const [minValue, setMinValue] = useState(1e6);
  const [showExcluded, setShowExcluded] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "gap", dir: -1 });
  const [limit, setLimit] = useState(PAGE);
  const [selected, setSelected] = useState<number | null>(null);
  const select = (id: number) => {
    setSelected(id);
    // On narrow screens the detail panel sits below the table, so bring it into view.
    if (window.innerWidth < 900) {
      requestAnimationFrame(() => document.getElementById("player-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  };

  const leagues = useMemo(
    () => Object.entries(meta.leagues).filter(([k]) => k !== "Other").sort((a, b) => a[1].localeCompare(b[1])),
    [meta],
  );

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = players.filter(
      (p) =>
        (!needle || p.name.toLowerCase().includes(needle) || p.club.toLowerCase().includes(needle)) &&
        (league === "all" || p.league === league) &&
        (pos === "all" || p.pos === pos) &&
        p.age <= maxAge &&
        p.min >= minMin &&
        p.value >= minValue &&
        (showExcluded || !p.excluded || league === p.league),
    );
    const { key, dir } = sort;
    filtered.sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      return (typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number)) * dir;
    });
    return filtered;
  }, [players, q, league, pos, maxAge, minMin, minValue, showExcluded, sort]);

  const current = players.find((p) => p.id === selected) ?? rows[0] ?? null;

  const header = (key: SortKey, label: string, num = true, extra = "") => (
    <th
      className={`sortable${num ? " num" : ""}${extra}`}
      onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((-s.dir) as 1 | -1) : key === "name" ? 1 : -1 }))}
      aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      {label}
      {sort.key === key ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
    </th>
  );

  const resetLimit = <T,>(fn: (v: T) => void) => (v: T) => {
    fn(v);
    setLimit(PAGE);
  };

  return (
    <>
      <h1>Scouting list</h1>
      <p className="lede">
        Players ranked by how far the model's fair value sits above their latest Transfermarkt market value. The model
        only sees minutes, goals, assists, team strength, league, age and position, so treat the list as a starting point
        for scouting, not a verdict.
      </p>
      <div className={`refresh-note${info.stale ? " is-stale" : ""}`} role="note">
        <span className="refresh-dot" aria-hidden="true" />
        Market values as of {info.valuesAsOf} · performance from {info.statsSeason}
        {info.stale ? " · upstream data updates are paused" : ` · rebuilt ${info.refreshed}`}
      </div>
      <div className="filters" role="group" aria-label="Filters">
        <label className="field">
          Search player or club
          <input type="search" value={q} placeholder="e.g. Getafe" onChange={(e) => resetLimit(setQ)(e.target.value)} />
        </label>
        <label className="field">
          League
          <select value={league} onChange={(e) => resetLimit(setLeague)(e.target.value)}>
            <option value="all">All leagues</option>
            {leagues.map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Position
          <select value={pos} onChange={(e) => resetLimit(setPos)(e.target.value)}>
            <option value="all">All</option>
            {["Attack", "Midfield", "Defender", "Goalkeeper"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Max age
          <select value={maxAge} onChange={(e) => resetLimit(setMaxAge)(Number(e.target.value))}>
            {[21, 23, 26, 29, 40].map((a) => (
              <option key={a} value={a}>
                {a === 40 ? "Any" : `≤ ${a}`}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          League minutes
          <select value={minMin} onChange={(e) => resetLimit(setMinMin)(Number(e.target.value))}>
            {[900, 1500, 2000, 2500].map((m) => (
              <option key={m} value={m}>
                ≥ {m.toLocaleString()}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Market value
          <select value={minValue} onChange={(e) => resetLimit(setMinValue)(Number(e.target.value))}>
            {[0, 1e6, 5e6, 20e6].map((v) => (
              <option key={v} value={v}>
                {v === 0 ? "Any" : `≥ ${eur(v)}`}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={showExcluded} onChange={(e) => resetLimit(setShowExcluded)(e.target.checked)} />
          Include Russia &amp; Ukraine
        </label>
      </div>

      <div className="scout">
        <div>
          <div className="small muted" style={{ marginBottom: 8 }}>
            {rows.length.toLocaleString()} players · click a row for details
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {header("name", "Player", false)}
                  {header("gap", "Gap")}
                  {header("value", "Market")}
                  {header("model", "Model", true, " hide-sm")}
                  {header("age", "Age")}
                  <th className="hide-sm">Pos</th>
                  {header("ga90", "G+A/90", true, " hide-md")}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, limit).map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => select(p.id)}
                    onKeyDown={(e) => e.key === "Enter" && select(p.id)}
                    tabIndex={0}
                    aria-selected={current?.id === p.id}
                  >
                    <td className="player-td">
                      <div className="player-cell">
                        <span>
                          {p.name}
                          {p.excluded && <span className="tag">structural break</span>}
                        </span>
                        <span className="club">
                          {p.club} · {meta.leagues[p.league] ?? p.league}
                        </span>
                      </div>
                    </td>
                    <td className={`num ${p.gap >= 0 ? "gap-pos" : "gap-neg"}`}>{signedPct(p.gap)}</td>
                    <td className="num">{eur(p.value)}</td>
                    <td className="num hide-sm">{eur(p.model)}</td>
                    <td className="num">{p.age}</td>
                    <td className="hide-sm" title={p.sub ?? p.pos}>
                      {POS_ABBR[p.sub ?? p.pos] ?? p.sub ?? p.pos}
                    </td>
                    <td className="num hide-md">{p.ga90.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <div className="empty">No players match these filters.</div>}
          </div>
          {rows.length > limit && (
            <button className="theme-btn more" onClick={() => setLimit((l) => l + PAGE)}>
              Show {Math.min(PAGE, rows.length - limit)} more
            </button>
          )}
        </div>
        <div className="detail" id="player-detail">{current && <PlayerDetail p={current} meta={meta} info={info} palette={palette} />}</div>
      </div>
    </>
  );
}

function PlayerDetail({ p, meta, info, palette }: { p: Player; meta: Meta; info: ScoutingInfo; palette: Palette }) {
  const histories = useJson<Histories>("histories");
  const history = useMemo(
    () => (histories?.[String(p.id)] ?? []).map(([d, v]) => ({ t: Date.parse(d), d, v: v / 1e6 })),
    [histories, p.id],
  );
  const shapRows = p.shap.map(([f, v]) => ({ label: SHORT_FEATURE[f] ?? meta.features[f] ?? f, value: v }));
  const yearTicks = useMemo(() => {
    if (!history.length) return undefined;
    const first = new Date(history[0].t).getFullYear() + 1;
    const last = new Date(history[history.length - 1].t).getFullYear();
    const step = Math.max(1, Math.ceil((last - first + 1) / 6));
    const ticks: number[] = [];
    for (let y = first; y <= last; y += step) ticks.push(Date.UTC(y, 0, 1));
    return ticks.length >= 2 ? ticks : undefined;
  }, [history]);
  return (
    <section className="card" aria-live="polite">
      <div className="detail-head">
        <div>
          <div className="detail-name">{p.name}</div>
          <div className="muted small">
            {p.sub ?? p.pos} · {p.club} · {meta.leagues[p.league] ?? p.league} · age {p.age}
          </div>
          {p.now && <div className="small" style={{ marginTop: 2 }}>Now at {p.now}</div>}
        </div>
      </div>
      <div className="value-pair">
        <div>
          <span title={`Latest Transfermarkt valuation, ${p.valueDate}`}>Market value</span>
          <b>{eur(p.value)}</b>
          <span>as of {p.valueDate.slice(0, 7)}</span>
        </div>
        <div>
          <span>Model fair value</span>
          <b>{eur(p.model)}</b>
        </div>
        <div>
          <span>Gap</span>
          <b className={p.gap >= 0 ? "gap-pos" : "gap-neg"}>{signedPct(p.gap)}</b>
        </div>
      </div>

      <h3 style={{ fontSize: "0.9rem" }}>Market value history</h3>
      <div style={{ height: 190, marginTop: 6 }}>
        {history.length === 0 ? (
          <div className="empty">{histories ? "No valuation history." : "Loading…"}</div>
        ) : (
          <ResponsiveContainer>
            <LineChart data={history} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke={palette.grid} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                ticks={yearTicks}
                tickFormatter={(t) =>
                  yearTicks
                    ? String(new Date(t).getUTCFullYear())
                    : new Date(t).toLocaleDateString(undefined, { month: "short", year: "2-digit" })
                }
                tickLine={false}
                axisLine={{ stroke: palette.axis }}
                minTickGap={28}
              />
              <YAxis tickFormatter={(v) => `€${v}m`} tickLine={false} axisLine={false} width={52} />
              <ReferenceLine
                y={p.model / 1e6}
                stroke={palette.muted}
                strokeWidth={1}
                label={{ value: "model fair value", position: "insideTopLeft", fontSize: 11 }}
              />
              <Tooltip
                content={(tp) => (
                  <TooltipBox
                    {...(tp as object)}
                    title={(l) => new Date(Number(l)).toLocaleDateString(undefined, { year: "numeric", month: "short" })}
                    fmt={(v) => eur(v * 1e6)}
                    names={{ v: "Market value" }}
                  />
                )}
              />
              <Line
                type="stepAfter"
                dataKey="v"
                stroke={palette.series[0]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: palette.surface, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <h3 style={{ fontSize: "0.9rem", marginTop: 14 }}>Why the model values him here</h3>
      <div className="muted small" style={{ marginBottom: 6 }}>
        Largest SHAP contributions to the model's estimate, relative to a typical player that season
      </div>
      <DivergingBars
        rows={shapRows}
        pos={palette.pos}
        neg={palette.neg}
        grid={palette.grid}
        muted={palette.muted}
        fmt={(v) => signedPct(v)}
        labelWidth={136}
      />
      <div className="stats">
        <div>
          <span>League minutes</span>
          {p.min.toLocaleString()}
        </div>
        <div>
          <span>Goals / assists</span>
          {p.g} / {p.a}
        </div>
        <div>
          <span>European minutes</span>
          {p.euroMin.toLocaleString()}
        </div>
        <div>
          <span>Contract until</span>
          {p.contract ? p.contract.slice(0, 7) : "–"}
        </div>
      </div>
      <p className="note">
        {p.excluded &&
          "Russian and Ukrainian club values have been structurally lower since 2022, which the model cannot learn from earlier seasons, so this gap is likely overstated. "}
        Performance and club are from {info.statsSeason}; the model is trained on {info.trainSeasons}. Explanations
        come from an equivalent LightGBM model (R² {meta.shapCheck.r2_lightgbm}, residuals correlated{" "}
        {meta.shapCheck.residual_correlation} with the main model).
      </p>
    </section>
  );
}
