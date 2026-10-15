import { useEffect, useMemo, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  ErrorBar,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Insights as Ins, Meta } from "../data";
import { signedPct } from "../data";
import type { Palette } from "../theme";
import { ChartCard, Legend } from "./ChartCard";
import { DecileChart } from "./Overview";
import { DivergingBars, RoundedBar, TooltipBox } from "./chartParts";

const POSITIONS = ["Attack", "Midfield", "Defender", "Goalkeeper"];
const BUY = ["GB1", "IT1", "FR1", "ES1", "L1", "Other"];

function termLabel(term: string, leagues: Record<string, string>) {
  const m = term.match(/\[T\.(.+)\]$/);
  const lvl = m ? m[1] : term;
  if (term.includes("buy_group")) return `Buyer: ${leagues[lvl] ?? lvl}`;
  if (term.includes("age_band")) return lvl === "U21" ? "Age under 21" : `Age ${lvl}`;
  if (term === "deadline_week") return "Deadline week";
  if (term === "winter_window") return "Winter window";
  return term;
}

export function Insights({ ins, meta, palette, anchor }: { ins: Ins; meta: Meta; palette: Palette; anchor?: string }) {
  useEffect(() => {
    if (anchor) document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [anchor]);
  return (
    <>
      <h1>Market insights</h1>
      <p className="lede">
        Four questions about how the transfer market prices players, each with the method behind the answer. Every chart
        has a table view.
      </p>
      <Premiums ins={ins} meta={meta} palette={palette} />
      <Tournaments ins={ins} palette={palette} />
      <Model ins={ins} meta={meta} palette={palette} />
      <Ages ins={ins} palette={palette} />
    </>
  );
}

function Premiums({ ins, meta, palette }: { ins: Ins; meta: Meta; palette: Palette }) {
  const [on, setOn] = useState<Record<string, boolean>>(() => Object.fromEntries(BUY.map((k) => [k, true])));
  const color = (k: string) => palette.series[BUY.indexOf(k)];
  const names = Object.fromEntries(BUY.map((k) => [k, meta.leagues[k] ?? k]));
  const effects = ins.premiumEffects
    .filter((e) => e.term.includes("buy_group") || e.term.includes("age_band") || e.term.includes("deadline"))
    .map((e) => ({ label: termLabel(e.term, meta.leagues), value: e.effect, lo: e.lo, hi: e.hi }))
    .sort((a, b) => b.value - a.value);
  const quant = useMemo(() => {
    const rows = ins.quantile.filter((q) => q.quantile !== "OLS");
    const qs = [...new Set(rows.map((r) => Number(r.quantile)))];
    return qs.map((q) => ({
      q: `${Math.round(q * 100)}th`,
      ...Object.fromEntries(rows.filter((r) => Number(r.quantile) === q).map((r) => [r.term, r.effect])),
    }));
  }, [ins]);
  const qTerms = ["Premier League buyer", "Under-21 player", "Serie A buyer"];
  return (
    <>
      <h2 id="premiums">Who overpays?</h2>
      <p className="section-lede">
        Premium = transfer fee ÷ the player's market value just before the move. Across all paid transfers the median deal
        is slightly <em>below</em> market value; the buyer's league is what moves it.
      </p>
      <div className="grid-2">
        <ChartCard
          title="Median fee vs. market value, by buying league"
          subtitle="3-season rolling median · 15,983 paid transfers"
          rows={ins.premiumTrend}
          columns={[
            { key: "season", label: "Season" },
            ...BUY.map((k) => ({ key: k, label: names[k], num: true, fmt: (r: Record<string, number | null>) => (r[k] == null ? "–" : signedPct(r[k] as number)) })),
          ]}
          extra={
            <div className="chips" role="group" aria-label="Leagues shown">
              {BUY.map((k) => (
                <button key={k} className="chip" aria-pressed={on[k]} onClick={() => setOn((o) => ({ ...o, [k]: !o[k] }))}>
                  <i className="key" style={{ background: color(k) }} />
                  {names[k]}
                </button>
              ))}
            </div>
          }
        >
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={ins.premiumTrend} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke={palette.grid} />
                <XAxis dataKey="season" tickLine={false} axisLine={{ stroke: palette.axis }} />
                <YAxis tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} />
                <ReferenceLine y={0} stroke={palette.axis} />
                <Tooltip content={(p) => <TooltipBox {...(p as object)} title={(l) => `${l}/${String(Number(l) + 1).slice(2)}`} fmt={(v) => signedPct(v)} names={names} />} />
                {BUY.filter((k) => on[k]).map((k) => (
                  <Line
                    key={k}
                    dataKey={k}
                    stroke={color(k)}
                    strokeWidth={k === "GB1" ? 2.5 : 2}
                    dot={false}
                    activeDot={{ r: 4, stroke: palette.surface, strokeWidth: 2 }}
                    isAnimationActive={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
        <ChartCard
          title="What drives the premium"
          subtitle="OLS on log(fee ÷ market value), controls for seller, position, value, season · 95% CI · vs. buyers outside the big five, age 24–26"
          rows={effects}
          columns={[
            { key: "label", label: "Factor" },
            { key: "value", label: "Effect", num: true, fmt: (r) => signedPct(r.value, 1) },
            { key: "lo", label: "95% CI", num: true, fmt: (r) => `${signedPct(r.lo!)} to ${signedPct(r.hi!)}` },
          ]}
        >
          <DivergingBars rows={effects} pos={palette.pos} neg={palette.neg} grid={palette.grid} muted={palette.muted} fmt={(v) => signedPct(v)} />
        </ChartCard>
      </div>
      <div style={{ marginTop: 16 }}>
        <ChartCard
          title="Is the English premium driven by a few blockbuster overpays?"
          subtitle="Quantile regression: effect at each percentile of the fee-to-value distribution. English clubs rarely get bargains (largest premium at the bottom); the youth premium grows toward the top."
          rows={quant}
          columns={[{ key: "q", label: "Percentile" }, ...qTerms.map((t) => ({ key: t, label: t, num: true, fmt: (r: Record<string, string | number>) => signedPct(Number(r[t])) }))]}
        >
          <div style={{ height: 240 }}>
            <ResponsiveContainer>
              <LineChart data={quant} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke={palette.grid} />
                <XAxis dataKey="q" tickLine={false} axisLine={{ stroke: palette.axis }} />
                <YAxis tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} domain={[0, "auto"]} />
                <Tooltip content={(p) => <TooltipBox {...(p as object)} title={(l) => `${l} percentile`} fmt={(v) => signedPct(v)} />} />
                {qTerms.map((t, i) => (
                  <Line key={t} dataKey={t} stroke={[palette.series[0], palette.series[1], palette.series[2]][i]} strokeWidth={2} dot={{ r: 4, fill: [palette.series[0], palette.series[1], palette.series[2]][i], strokeWidth: 0 }} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <Legend items={qTerms.map((t, i) => ({ label: t, color: [palette.series[0], palette.series[1], palette.series[2]][i] }))} />
        </ChartCard>
      </div>
    </>
  );
}

function Tournaments({ ins, palette }: { ins: Ins; palette: Palette }) {
  const data = useMemo(() => {
    const main = ins.eventStudy.filter((e) => e.spec === "plus_momentum");
    const naive = ins.eventStudy.filter((e) => e.spec === "value_age_position");
    const qs = [...new Set(main.map((e) => e.quarter))].sort((a, b) => a - b);
    const rows: Record<string, number | string | number[] | null>[] = [];
    for (const q of qs) {
      if (q === 1) rows.push({ label: "Tournament", main: null, naive: null, band: null });
      const m = main.find((e) => e.quarter === q)!;
      const n = naive.find((e) => e.quarter === q);
      rows.push({ label: q < 0 ? `Q${q}` : `Q+${q}`, main: m.effect, naive: n?.effect ?? null, band: [m.lo, m.hi], lo: m.lo, hi: m.hi, treated: m.treated });
    }
    return rows;
  }, [ins]);
  const dose = useMemo(() => {
    const groups = ["1", "2", "3+"];
    return groups.map((g) => {
      const six = ins.dose.find((d) => d.contrib === g && d.quarter === 2)!;
      const twelve = ins.dose.find((d) => d.contrib === g && d.quarter === 4)!;
      return {
        label: `${g} goal${g === "1" ? "" : "s"} + assists`.replace("1 goal + assists", "1 goal or assist").replace("2 goals + assists", "2 goals/assists").replace("3+ goals + assists", "3+ goals/assists"),
        six: six.effect,
        twelve: twelve.effect,
        sixErr: [six.effect - six.lo, six.hi - six.effect],
        twelveErr: [twelve.effect - twelve.lo, twelve.hi - twelve.effect],
        n: twelve.n,
      };
    });
  }, [ins]);
  const pl = ins.placebo;
  return (
    <>
      <h2 id="tournaments">Does a good tournament raise a player's price?</h2>
      <p className="section-lede">
        Scorers and assisters at 7 tournaments (World Cups 2014–2022, Euros 2016–2024, Copa América 2024) compared with
        international players of the same tournament, position, age, value and pre-tournament form.
      </p>
      <div className="grid-2">
        <ChartCard
          title="Extra change in market value vs. matched peers"
          subtitle="Relative to the last pre-tournament value · shaded band = 95% CI of the main estimate"
          rows={data.filter((d) => d.label !== "Tournament")}
          columns={[
            { key: "label", label: "Quarter" },
            { key: "main", label: "Main estimate", num: true, fmt: (r) => signedPct(Number(r.main), 1) },
            { key: "naive", label: "Without form matching", num: true, fmt: (r) => (r.naive == null ? "–" : signedPct(Number(r.naive), 1)) },
            { key: "treated", label: "Scorers", num: true },
          ]}
        >
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke={palette.grid} />
                <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: palette.axis }} interval={0} fontSize={11} />
                <YAxis tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} />
                <ReferenceLine y={0} stroke={palette.axis} />
                <ReferenceLine x="Tournament" stroke={palette.series[3]} strokeWidth={10} strokeOpacity={0.25} />
                <Tooltip
                  content={(p) => (
                    <TooltipBox {...(p as object)} fmt={(v) => signedPct(v, 1)} names={{ main: "Main estimate", naive: "Without form matching" }} />
                  )}
                />
                <Area dataKey="band" stroke="none" fill={palette.band} isAnimationActive={false} connectNulls activeDot={false} />
                <Line dataKey="naive" stroke={palette.muted} strokeWidth={1.5} dot={{ r: 3, fill: palette.muted, strokeWidth: 0 }} isAnimationActive={false} connectNulls />
                <Line dataKey="main" stroke={palette.series[0]} strokeWidth={2} dot={{ r: 4, fill: palette.series[0], stroke: palette.surface, strokeWidth: 2 }} isAnimationActive={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <Legend items={[{ label: "Main estimate (matched on form)", color: palette.series[0] }, { label: "Without form matching", color: palette.muted }]} />
        </ChartCard>
        <ChartCard
          title="More goals and assists, bigger bump"
          subtitle="Extra change vs. matched peers · 95% CI"
          rows={dose}
          columns={[
            { key: "label", label: "Contributions" },
            { key: "six", label: "6 months", num: true, fmt: (r) => signedPct(r.six, 1) },
            { key: "twelve", label: "12 months", num: true, fmt: (r) => signedPct(r.twelve, 1) },
            { key: "n", label: "Players", num: true },
          ]}
        >
          <div style={{ height: 230 }}>
            <ResponsiveContainer>
              <BarChart data={dose} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={2}>
                <CartesianGrid vertical={false} stroke={palette.grid} />
                <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: palette.axis }} fontSize={11} />
                <YAxis tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} />
                <Tooltip cursor={{ fill: palette.grid, opacity: 0.5 }} content={(p) => <TooltipBox {...(p as object)} fmt={(v) => signedPct(v, 1)} names={{ six: "6 months after", twelve: "12 months after" }} />} />
                <Bar dataKey="six" fill={palette.series[2]} maxBarSize={24} shape={(s: object) => <RoundedBar {...s} />} isAnimationActive={false}>
                  <ErrorBar dataKey="sixErr" width={4} stroke={palette.muted} strokeWidth={1.5} />
                </Bar>
                <Bar dataKey="twelve" fill={palette.series[0]} maxBarSize={24} shape={(s: object) => <RoundedBar {...s} />} isAnimationActive={false}>
                  <ErrorBar dataKey="twelveErr" width={4} stroke={palette.muted} strokeWidth={1.5} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <Legend items={[{ label: "6 months after", color: palette.series[2], shape: "box" }, { label: "12 months after", color: palette.series[0], shape: "box" }]} />
          {pl.length > 0 && (
            <p className="note">
              Placebo test: shuffling the scorer label 1,000 times within matching cells gives effects centred on 0% and
              never above +{pl[pl.length - 1].placebo_max_pct.toFixed(1)}% at 12 months (real +
              {pl[pl.length - 1].real_effect_pct.toFixed(1)}%, p = {pl[pl.length - 1].permutation_p.toFixed(3)}).
            </p>
          )}
        </ChartCard>
      </div>
    </>
  );
}

function Model({ ins, meta, palette }: { ins: Ins; meta: Meta; palette: Palette }) {
  const imp = ins.shapImportance.slice(0, 10).map((s) => ({ label: meta.features[s.feature] ?? s.feature, value: s.swing }));
  return (
    <>
      <h2 id="model">Can undervalued players be spotted in advance?</h2>
      <p className="section-lede">
        A gradient-boosting model predicts each player's market value from that season's performance and context. Trained
        only on earlier seasons, it reaches an out-of-sample R² of {Math.min(...ins.metrics.map((m) => m.r2)).toFixed(2)}–
        {Math.max(...ins.metrics.map((m) => m.r2)).toFixed(2)}.
      </p>
      <div className="grid-2">
        <ChartCard
          title="Next-year value growth vs. market, by model decile"
          subtitle="Decile 1 = most undervalued · backtest 2018/19–2024/25 · 95% CI"
          rows={ins.metrics}
          columns={[
            { key: "season", label: "Test season" },
            { key: "r2", label: "R² (model)", num: true },
            { key: "r2Linear", label: "R² (linear)", num: true },
            { key: "medianErr", label: "Median error", num: true, fmt: (r) => `${r.medianErr}%` },
          ]}
        >
          <DecileChart ins={ins} palette={palette} />
        </ChartCard>
        <ChartCard
          title="What the model relies on"
          subtitle="Typical effect of each feature on predicted value (mean |SHAP|, 2025/26). Context outweighs individual output."
          rows={imp}
          columns={[
            { key: "label", label: "Feature" },
            { key: "value", label: "Typical effect", num: true, fmt: (r) => `±${r.value.toFixed(0)}%` },
          ]}
        >
          <DivergingBars rows={imp} pos={palette.series[2]} neg={palette.neg} grid={palette.grid} muted={palette.muted} fmt={(v) => `±${v.toFixed(0)}%`} labelWidth={160} />
        </ChartCard>
      </div>
    </>
  );
}

function Ages({ ins, palette }: { ins: Ins; palette: Palette }) {
  const [pos, setPos] = useState("Attack");
  const curve = ins.ageCurves[pos];
  const data = curve.points.map((p) => ({ age: p.age, delta: p.delta == null ? null : p.delta * 100, naive: p.naive == null ? null : p.naive * 100 }));
  const at = (age: number, k: "delta" | "naive") => data.find((d) => d.age === age)?.[k];
  return (
    <>
      <h2 id="ages">When does value peak, and how fast does it fall?</h2>
      <p className="section-lede">
        Comparing different players at each age (naive) makes older cohorts look too good, because weaker players drop
        out of the data. Following each player's own year-to-year change (delta method) removes that survivorship bias.
      </p>
      <ChartCard
        title={`${pos}: market value relative to peak`}
        subtitle={`Peak at ${curve.peak} · at 32 the naive curve keeps ${Math.round(at(32, "naive") ?? 0)}% of peak value, the within-player curve ${Math.round(at(32, "delta") ?? 0)}%`}
        rows={data}
        columns={[
          { key: "age", label: "Age" },
          { key: "delta", label: "Within-player", num: true, fmt: (r) => (r.delta == null ? "–" : `${r.delta.toFixed(0)}%`) },
          { key: "naive", label: "Naive", num: true, fmt: (r) => (r.naive == null ? "–" : `${r.naive.toFixed(0)}%`) },
        ]}
        extra={
          <div className="seg" role="group" aria-label="Position" style={{ marginBottom: 10 }}>
            {POSITIONS.map((p) => (
              <button key={p} aria-pressed={pos === p} onClick={() => setPos(p)}>
                {p}
              </button>
            ))}
          </div>
        }
      >
        <div style={{ height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 20, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke={palette.grid} />
              <XAxis dataKey="age" tickLine={false} axisLine={{ stroke: palette.axis }} />
              <YAxis tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} domain={[0, 100]} />
              <ReferenceLine x={32} stroke={palette.grid} strokeWidth={1} label={{ value: "32", position: "top", fontSize: 11 }} />
              <Tooltip content={(p) => <TooltipBox {...(p as object)} title={(l) => `Age ${l}`} fmt={(v) => `${v.toFixed(0)}% of peak`} names={{ delta: "Within-player", naive: "Naive" }} />} />
              <Line dataKey="naive" stroke={palette.series[1]} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: palette.surface, strokeWidth: 2 }} isAnimationActive={false} connectNulls />
              <Line dataKey="delta" stroke={palette.series[0]} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: palette.surface, strokeWidth: 2 }} isAnimationActive={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <Legend items={[{ label: "Within-player (delta method)", color: palette.series[0] }, { label: "Naive cross-section", color: palette.series[1] }]} />
      </ChartCard>
    </>
  );
}
