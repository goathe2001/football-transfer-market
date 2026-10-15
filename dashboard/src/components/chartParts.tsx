import { useEffect, useRef, useState } from "react";

/** Recharts tooltip: value leads, series name follows, short line key per row. */
export function TooltipBox({
  active,
  payload,
  label,
  title,
  fmt,
  names,
}: {
  active?: boolean;
  payload?: { dataKey?: string | number; value?: unknown; color?: string; stroke?: string; name?: string }[];
  label?: string | number;
  title?: (label: string | number | undefined) => string;
  fmt: (v: number) => string;
  names?: Record<string, string>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const rows = payload.filter((p) => typeof p.value === "number");
  if (rows.length === 0) return null;
  rows.sort((a, b) => (b.value as number) - (a.value as number));
  return (
    <div className="tt">
      <div className="tt-title">{title ? title(label) : String(label)}</div>
      {rows.map((p) => (
        <div className="tt-row" key={String(p.dataKey)}>
          <span className="lbl">
            <i className="key" style={{ background: p.stroke || p.color }} />
            {names?.[String(p.dataKey)] ?? p.name ?? String(p.dataKey)}
          </span>
          <b>{fmt(p.value as number)}</b>
        </div>
      ))}
    </div>
  );
}

/** Bar shape with a 4px rounded data end and a square baseline end, for either sign and layout. */
export function RoundedBar(props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  fill?: string;
  value?: number | number[];
  layout?: "horizontal" | "vertical";
}) {
  let { x = 0, y = 0, width = 0, height = 0 } = props;
  const v = Array.isArray(props.value) ? props.value[1] - props.value[0] : props.value ?? 0;
  if (width < 0) {
    x += width;
    width = -width;
  }
  if (height < 0) {
    y += height;
    height = -height;
  }
  const r = Math.min(4, width / 2, height / 2);
  const horizontalBars = props.layout === "vertical";
  let d: string;
  if (!horizontalBars) {
    // columns: data end is the top for positive values, the bottom for negative ones
    d =
      v >= 0
        ? `M${x},${y + height}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${y + height}Z`
        : `M${x},${y}V${y + height - r}Q${x},${y + height} ${x + r},${y + height}H${x + width - r}Q${x + width},${y + height} ${x + width},${y + height - r}V${y}Z`;
  } else {
    d =
      v >= 0
        ? `M${x},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${y + height - r}Q${x + width},${y + height} ${x + width - r},${y + height}H${x}Z`
        : `M${x + width},${y}H${x + r}Q${x},${y} ${x},${y + r}V${y + height - r}Q${x},${y + height} ${x + r},${y + height}H${x + width}Z`;
  }
  return <path d={d} fill={props.fill} />;
}

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return { ref, width };
}

export type BarRow = { label: string; value: number; lo?: number; hi?: number; note?: string };

/** Horizontal bars growing from zero (either direction), optional CI whiskers, value at the tip. */
export function DivergingBars({
  rows,
  pos,
  neg,
  grid,
  muted,
  fmt,
  labelWidth = 170,
}: {
  rows: BarRow[];
  pos: string;
  neg: string;
  grid: string;
  muted: string;
  fmt: (v: number) => string;
  labelWidth?: number;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const rowH = 30;
  const barH = 16;
  const narrow = width < 460;
  const lw = narrow ? Math.min(labelWidth, 120) : labelWidth;
  const valuePad = 56;
  const plotW = Math.max(80, width - lw - valuePad * 2);
  const vals = rows.flatMap((r) => [r.value, r.lo ?? r.value, r.hi ?? r.value, 0]);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const sx = (v: number) => lw + valuePad + ((v - min) / span) * plotW;
  const zero = sx(0);
  const h = rows.length * rowH + 8;
  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width={width} height={h} role="img" aria-label="Bar chart" style={{ display: "block" }}>
        <line x1={zero} x2={zero} y1={0} y2={h} stroke={grid} strokeWidth={1} />
        {rows.map((r, i) => {
          const y = 4 + i * rowH;
          const x0 = Math.min(zero, sx(r.value));
          const w = Math.abs(sx(r.value) - zero);
          const color = r.value >= 0 ? pos : neg;
          const tipX = r.value >= 0 ? Math.max(sx(r.value), sx(r.hi ?? r.value)) + 6 : Math.min(sx(r.value), sx(r.lo ?? r.value)) - 6;
          return (
            <g
              key={r.label}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              tabIndex={0}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              style={{ outline: "none" }}
            >
              <rect x={0} y={y - 2} width={width} height={rowH} fill={hover === i ? grid : "transparent"} opacity={0.5} />
              <text x={lw - 8} y={y + barH / 2 + 4} textAnchor="end" fontSize={12} fill="currentColor" style={{ color: "var(--ink-2)" }}>
                {narrow && r.label.length > 20 ? r.label.slice(0, 19) + "…" : r.label}
              </text>
              <RoundedBar x={x0} y={y} width={Math.max(w, 1)} height={barH} fill={color} value={r.value} layout="vertical" />
              {r.lo !== undefined && r.hi !== undefined && (
                <g stroke={muted} strokeWidth={1.5}>
                  <line x1={sx(r.lo)} x2={sx(r.hi)} y1={y + barH / 2} y2={y + barH / 2} />
                  <line x1={sx(r.lo)} x2={sx(r.lo)} y1={y + 4} y2={y + barH - 4} />
                  <line x1={sx(r.hi)} x2={sx(r.hi)} y1={y + 4} y2={y + barH - 4} />
                </g>
              )}
              <text
                x={tipX}
                y={y + barH / 2 + 4}
                textAnchor={r.value >= 0 ? "start" : "end"}
                fontSize={12}
                fontWeight={600}
                fill="currentColor"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {fmt(r.value)}
              </text>
              <title>
                {r.label}: {fmt(r.value)}
                {r.lo !== undefined && r.hi !== undefined ? ` (95% CI ${fmt(r.lo)} to ${fmt(r.hi)})` : ""}
                {r.note ? ` — ${r.note}` : ""}
              </title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
