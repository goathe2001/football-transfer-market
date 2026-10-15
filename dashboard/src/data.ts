import { useEffect, useState } from "react";

export type Player = {
  id: number;
  name: string;
  age: number;
  pos: string;
  sub: string | null;
  club: string;
  league: string;
  min: number;
  apps: number;
  g: number;
  a: number;
  ga90: number;
  euroMin: number;
  value: number;
  model: number;
  gap: number;
  contract: string | null;
  excluded: boolean;
  /** Date of the market value shown (latest valuation). */
  valueDate: string;
  /** Current club, when it differs from the club in the stats season. */
  now: string | null;
  shap: [string, number][];
};

export type Insights = {
  ageCurves: Record<string, { peak: number; points: { age: number; delta: number | null; naive: number | null }[] }>;
  premiumTrend: Record<string, number | null>[];
  premiumEffects: { term: string; effect: number; lo: number; hi: number }[];
  quantile: { quantile: number | string; term: string; effect: number; lo: number | null; hi: number | null }[];
  eventStudy: { quarter: number; spec: string; effect: number; lo: number; hi: number; treated: number; control: number }[];
  dose: { quarter: number; contrib: string; effect: number; lo: number; hi: number; n: number }[];
  placebo: Record<string, number>[];
  deciles: { decile: number; growth: number; lo: number; hi: number; n: number }[];
  metrics: { season: string; r2: number; r2Linear: number; medianErr: number }[];
  shapImportance: { feature: string; swing: number }[];
};

export type Meta = {
  snapshot: string;
  season: string;
  leagues: Record<string, string>;
  features: Record<string, string>;
  excludedLeagues: string[];
  shapCheck: Record<string, number>;
  counts: Record<string, number>;
};

/** Written by analysis/07_refresh_scouting.py (run on demand from GitHub Actions). */
export type Scouting = {
  statsSeason: string;
  valuesAsOf: string;
  refreshed: string;
  /** True when the upstream dataset has stopped publishing new market values. */
  stale: boolean;
  players: number;
  trainSeasons: string;
};

export type Histories = Record<string, [string, number][]>;

const BASE = `${import.meta.env.BASE_URL}data/`;

export function useJson<T>(name: string, enabled = true): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    if (!enabled || data) return;
    let alive = true;
    fetch(`${BASE}${name}.json`)
      .then((r) => r.json())
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [name, enabled, data]);
  return data;
}

export const eur = (v: number) =>
  v >= 1e6 ? `€${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1)}m` : `€${Math.round(v / 1e3)}k`;
export const signedPct = (v: number, d = 0) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%`;
