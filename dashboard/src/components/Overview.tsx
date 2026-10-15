import { Bar, BarChart, Cell, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import type { Insights, Meta } from "../data";
import { signedPct } from "../data";
import type { Palette } from "../theme";
import { ChartCard } from "./ChartCard";
import { RoundedBar, TooltipBox } from "./chartParts";

type Tab = "overview" | "scouting" | "insights" | "about";

export function Overview({ ins, meta, palette, go }: { ins: Insights; meta: Meta; palette: Palette; go: (t: Tab, anchor?: string) => void }) {
  const placebo12 = ins.placebo.find((p) => p.quarter === 4);
  const tiles = [
    {
      value: "~2×",
      label: "Premier League clubs pay about twice the fee-to-market-value ratio of buyers outside the big five leagues.",
      method: "Regression on 15,983 paid transfers",
      anchor: "premiums",
    },
    {
      value: "+14%",
      label: "A goal or assist at a World Cup, Euro or Copa América lifts a player's value, and it lasts at least a year.",
      method: "Event study, 7 tournaments, placebo-tested",
      anchor: "tournaments",
    },
    {
      value: "+16%",
      label: "Players the model flags as undervalued outgrow the market the following season.",
      method: "Gradient boosting, walk-forward backtest",
      anchor: "model",
    },
    {
      value: "35%",
      label: "Value an attacker keeps at 32. Naive age curves say 62%, because weaker players drop out of the data.",
      method: "Within-player (delta method) age curves",
      anchor: "ages",
    },
  ];
  return (
    <>
      <h1>Is the football transfer market rational?</h1>
      <p className="lede">
        An interactive companion to an analysis of {meta.counts.transfers.toLocaleString()} transfers,{" "}
        {meta.counts.valuations.toLocaleString()} market valuations and {meta.counts.appearances.toLocaleString()} match
        appearances from Transfermarkt. Explore where clubs overpay, what moves a player's price, and which players look
        undervalued right now.
      </p>
      <div className="tiles">
        {tiles.map((t) => (
          <button key={t.value} className="card tile" onClick={() => go("insights", t.anchor)}>
            <span className="tile-value">{t.value}</span>
            <span className="tile-label">{t.label}</span>
            <span className="tile-method">{t.method} →</span>
          </button>
        ))}
      </div>

      <h2>The model's bargains really do appreciate</h2>
      <p className="section-lede">
        Each season, players are ranked by how far their market value sits below (decile 1) or above (decile 10) a
        performance-based model trained only on earlier seasons. The following year, undervalued players gain value
        relative to the market and overvalued ones lose it.
      </p>
      <div className="grid-2">
        <ChartCard
          title="Next-year value growth vs. market, by model decile"
          subtitle="Backtest 2018/19–2024/25 · 23,348 player-seasons · 95% CI"
          rows={ins.deciles}
          columns={[
            { key: "decile", label: "Decile" },
            { key: "growth", label: "Growth vs. market", num: true, fmt: (r) => signedPct(r.growth, 1) },
            { key: "n", label: "Players", num: true, fmt: (r) => r.n.toLocaleString() },
          ]}
        >
          <DecileChart ins={ins} palette={palette} />
        </ChartCard>
        <section className="card">
          <h3>Try it</h3>
          <p className="card-sub" style={{ marginBottom: 12 }}>
            The {meta.season} scouting list ranks {(3598).toLocaleString()} players by the gap between model fair value and
            market value. Filter by league, position and age, then open a player to see his value history and why the
            model rates him where it does.
          </p>
          <button className="theme-btn" onClick={() => go("scouting")} style={{ color: "var(--ink)" }}>
            Open the scouting list →
          </button>
          <p className="note">
            Robustness: shuffling the tournament "scored or assisted" label 1,000 times never produces an effect above{" "}
            {placebo12 ? `+${placebo12.placebo_max_pct.toFixed(1)}%` : "7%"} (real: +14.4%). Data snapshot{" "}
            {meta.snapshot}.
          </p>
        </section>
      </div>
    </>
  );
}

export function DecileChart({ ins, palette }: { ins: Insights; palette: Palette }) {
  const data = ins.deciles.map((d) => ({ ...d, label: String(d.decile), err: [d.growth - d.lo, d.hi - d.growth] }));
  return (
    <div style={{ height: 260 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 18, left: 0 }}>
          <CartesianGrid vertical={false} stroke={palette.grid} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={{ stroke: palette.axis }}
            label={{ value: "← undervalued        decile        overvalued →", position: "insideBottom", offset: -10, fontSize: 11 }}
          />
          <YAxis tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} />
          <Tooltip
            cursor={{ fill: palette.grid, opacity: 0.5 }}
            content={(p) => (
              <TooltipBox {...(p as object)} title={(l) => `Decile ${l}`} fmt={(v) => signedPct(v, 1)} names={{ growth: "Growth vs. market" }} />
            )}
          />
          <Bar dataKey="growth" shape={(s: object) => <RoundedBar {...s} />} maxBarSize={24} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.decile} fill={d.growth >= 0 ? palette.pos : palette.neg} />
            ))}
            <ErrorBar dataKey="err" width={4} stroke={palette.muted} strokeWidth={1.5} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
