import { ReactNode, useState } from "react";

type Column<T> = { key: keyof T | string; label: string; num?: boolean; fmt?: (row: T) => ReactNode };

export function ChartCard<T>({
  title,
  subtitle,
  children,
  rows,
  columns,
  extra,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  rows?: T[];
  columns?: Column<T>[];
  extra?: ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h3>{title}</h3>
          {subtitle && <div className="card-sub">{subtitle}</div>}
        </div>
        {rows && columns && (
          <button className="link-btn" onClick={() => setShowTable((s) => !s)} aria-expanded={showTable}>
            {showTable ? "Hide table" : "Show table"}
          </button>
        )}
      </div>
      {extra}
      {children}
      {showTable && rows && columns && (
        <div className="table-wrap mini-table">
          <table>
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={String(c.key)} className={c.num ? "num" : undefined}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={String(c.key)} className={c.num ? "num" : undefined}>
                      {c.fmt ? c.fmt(r) : String((r as Record<string, unknown>)[c.key as string] ?? "–")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function Legend({ items }: { items: { label: string; color: string; shape?: "line" | "box" }[] }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span key={it.label}>
          <i className={it.shape === "box" ? "key-box" : "key"} style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}
