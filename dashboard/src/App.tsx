import { useEffect, useState } from "react";
import type { Insights as Ins, Meta, Player, Scouting as ScoutingInfo } from "./data";
import { useJson } from "./data";
import { useTheme } from "./theme";
import { Overview } from "./components/Overview";
import { Scouting } from "./components/Scouting";
import { Insights } from "./components/Insights";
import { About } from "./components/About";
import { MoneyTable } from "./components/MoneyTable";
import type { MoneyHistory, MoneyLive } from "./components/MoneyTable";
import { Predictions } from "./components/Predictions";
import type { MatchModel, MatchPredictions } from "./components/Predictions";

type Tab = "overview" | "scouting" | "money" | "predictions" | "insights" | "about";
const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "scouting", label: "Scouting list" },
  { id: "money", label: "Money vs. table" },
  { id: "predictions", label: "Predictions" },
  { id: "insights", label: "Market insights" },
  { id: "about", label: "Method & data" },
];

function readHash(): Tab {
  const h = window.location.hash.replace("#", "") as Tab;
  return TABS.some((t) => t.id === h) ? h : "overview";
}

export default function App() {
  const { choice, setChoice, palette } = useTheme();
  const [tab, setTab] = useState<Tab>(readHash);
  const [anchor, setAnchor] = useState<string | undefined>();
  const players = useJson<Player[]>("players");
  const ins = useJson<Ins>("insights");
  const meta = useJson<Meta>("meta");
  const scouting = useJson<ScoutingInfo>("scouting");
  const money = useJson<MoneyHistory>("money_history", tab === "money");
  // Optional: written by the daily live-standings job; absent until it has run.
  const live = useJson<MoneyLive>("money_live", tab === "money");
  const matchModel = useJson<MatchModel>("match_model", tab === "predictions");
  // Optional: written by the daily job together with money_live.json.
  const predictions = useJson<MatchPredictions>("match_predictions", tab === "predictions");

  useEffect(() => {
    const onHash = () => setTab(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (t: Tab, a?: string) => {
    setAnchor(a);
    setTab(t);
    window.history.replaceState(null, "", `#${t}`);
    if (!a) window.scrollTo({ top: 0 });
  };
  const nextTheme = choice === "system" ? "dark" : choice === "dark" ? "light" : "system";
  const ready = players && ins && meta && scouting;

  return (
    <>
      <header className="top">
        <div className="wrap">
          <div className="brand">
            <span className="brand-dot" />
            Transfer Market Explorer
          </div>
          <button className="theme-btn" onClick={() => setChoice(nextTheme)} title={`Theme: ${choice} (click to change)`} aria-label={`Theme: ${choice}`}>
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" style={{ verticalAlign: "-2px" }}>
              <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 1.5a6.5 6.5 0 0 1 0 13z" fill="currentColor" />
            </svg>
            <span className="theme-label"> {choice === "system" ? "Auto" : choice === "dark" ? "Dark" : "Light"}</span>
          </button>
          <nav className="tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.id} className="tab" role="tab" aria-selected={tab === t.id} onClick={() => go(t.id)}>
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="wrap">
        {!ready ? (
          <div className="empty">Loading data…</div>
        ) : tab === "overview" ? (
          <Overview ins={ins} meta={meta} scouting={scouting} palette={palette} go={go} />
        ) : tab === "scouting" ? (
          <Scouting players={players} meta={meta} info={scouting} palette={palette} />
        ) : tab === "money" ? (
          money ? <MoneyTable history={money} live={live} meta={meta} palette={palette} /> : <div className="empty">Loading…</div>
        ) : tab === "predictions" ? (
          matchModel ? (
            <Predictions model={matchModel} live={predictions} meta={meta} palette={palette} />
          ) : (
            <div className="empty">Loading…</div>
          )
        ) : tab === "insights" ? (
          <Insights ins={ins} meta={meta} palette={palette} anchor={anchor} />
        ) : (
          <About meta={meta} scouting={scouting} />
        )}
      </main>
      <footer>
        <div className="wrap">
          Data from Transfermarkt via{" "}
          <a href="https://github.com/dcaribou/transfermarkt-datasets">transfermarkt-datasets</a>
          {meta ? `; research snapshot ${meta.snapshot}` : ""}
          {scouting ? `; scouting list market values as of ${scouting.valuesAsOf}` : ""}. Analysis and code:{" "}
          <a href="https://github.com/goathe2001/football-transfer-market">github.com/goathe2001/football-transfer-market</a>
        </div>
      </footer>
    </>
  );
}
