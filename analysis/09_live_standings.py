"""Step 9: live league tables vs. preseason squad value (run daily by GitHub Actions).

Fetches the current big-five standings from football-data.org, matches each team to its Transfermarkt
club, and compares actual points with the points expected from preseason squad value using the model
fitted in step 8 (money_history.json). Standard library only, so the daily job needs no database.

Environment
  FOOTBALL_DATA_TOKEN   free API key from https://www.football-data.org/client/register
                        (without it the script exits without changing anything)

Usage
  python analysis/09_live_standings.py                 # live API
  python analysis/09_live_standings.py --fixture DIR   # read <CODE>.json files from DIR instead (tests)

Writes dashboard/public/data/money_live.json.
"""
import argparse
import datetime as dt
import difflib
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboard" / "public" / "data"
API = "https://api.football-data.org/v4/competitions/{code}/standings"
# football-data.org competition code -> Transfermarkt league id
COMPETITIONS = {"PL": "GB1", "PD": "ES1", "SA": "IT1", "BL1": "L1", "FL1": "FR1"}

# Clubs whose names differ too much between the two sources for automatic matching.
OVERRIDES = {
    "fc bayern munchen": "bayern munich",
    "fc internazionale milano": "inter milan",
    "athletic club": "athletic bilbao",
    "olympique lyonnais": "olympique lyon",
    "olympique de marseille": "olympique marseille",
    "lille osc": "losc lille",
    "racing club de lens": "rc lens",
    "as roma": "associazione sportiva roma",
    "ac pisa 1909": "pisa sporting club",
}
STOP = {
    "fc", "afc", "cf", "ac", "sc", "ssc", "ss", "us", "as", "rc", "ca", "cd", "ud", "rcd", "sv", "vfb", "vfl",
    "tsg", "fsv", "osc", "club", "de", "del", "di", "calcio", "football", "futbol", "balompie", "spa", "s",
    "p", "a", "the", "of", "1", "fussballclub", "1846", "1899", "1901", "1907", "1909", "1910", "1913", "1919",
    "04", "05", "07", "29",
}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("ß", "ss")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def tokens(name: str) -> tuple:
    return tuple(t for t in norm(name).split() if t not in STOP)


def match_score(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    small, big = (set(ta), set(tb)) if len(ta) <= len(tb) else (set(tb), set(ta))
    if small <= big:
        return 0.9
    return difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio() * 0.85


def candidate_scores(team: dict, club: dict, exact_only: bool) -> float:
    names = [n for n in (team.get("name"), team.get("shortName")) if n]
    override = OVERRIDES.get(norm(names[0]))
    if override:
        return 1.0 if norm(club["name"]) == override else 0.0
    if exact_only:
        return 1.0 if any(tokens(n) and tokens(n) == tokens(club["name"]) for n in names) else 0.0
    return max(match_score(n, club["name"]) for n in names)


def assign(teams: list, league: str, clubs: list) -> list:
    """One-to-one matching of API teams to Transfermarkt clubs.

    Pass 1: clubs from the same league, allowing partial/fuzzy matches (score >= 0.8).
    Pass 2: teams still unmatched (usually newly promoted) against all clubs, exact names only,
    so a short name like "Deportivo" can never be matched to an unrelated club elsewhere.
    Within each pass, the highest-scoring pairs are fixed first and each club is used at most once.
    """
    result = [(None, 0.0)] * len(teams)
    used = set()
    for pool, exact_only in (([c for c in clubs if c["league"] == league], False), (clubs, True)):
        pairs = []
        for i, t in enumerate(teams):
            if result[i][0] is not None:
                continue
            for c in pool:
                score = candidate_scores(t, c, exact_only)
                if score >= 0.8:
                    pairs.append((score, c["value"], i, c))
        for score, _, i, c in sorted(pairs, key=lambda p: (-p[0], -p[1])):
            if result[i][0] is None and c["id"] not in used:
                result[i] = (c, score)
                used.add(c["id"])
    return result


def fetch(code: str, token: str, fixture: Path | None) -> dict:
    if fixture:
        return json.loads((fixture / f"{code}.json").read_text())
    req = urllib.request.Request(API.format(code=code), headers={"X-Auth-Token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def build(token: str, fixture: Path | None) -> dict:
    history = json.loads((DATA / "money_history.json").read_text())
    pre = json.loads((DATA / "preseason_live.json").read_text())
    model, min_players = history["model"], pre["minPlayers"]
    clubs = pre["clubs"]

    out = {"fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "valuesAsOf": pre["valuesAsOf"], "leagues": {}}
    for i, (code, league) in enumerate(COMPETITIONS.items()):
        if i and not fixture:
            time.sleep(7)  # free tier: 10 requests per minute
        data = fetch(code, token, fixture)
        table = next(s for s in data["standings"] if s.get("type") == "TOTAL")["table"]
        rows = []
        matches = assign([t["team"] for t in table], league, clubs)
        for t, (club, score) in zip(table, matches):
            complete = bool(club) and club["players"] >= min_players
            rows.append({
                "pos": t["position"], "team": t["team"].get("shortName") or t["team"]["name"],
                "teamName": t["team"]["name"],
                "crest": t["team"].get("crest"), "played": t["playedGames"], "points": t["points"],
                "gd": t["goalDifference"], "form": t.get("form"),
                "clubId": club["id"] if club else None, "club": club["name"] if club else None,
                "matchScore": round(score, 2), "value": club["value"] if club else None,
                "players": club["players"] if club else 0, "complete": complete,
            })
        logs = [math.log(r["value"]) for r in rows if r["complete"]]
        mean_log = sum(logs) / len(logs) if logs else 0.0
        for r in rows:
            if r["complete"] and r["played"] > 0:
                exp_ppg = model["intercepts"][league] + model["slope"] * (math.log(r["value"]) - mean_log)
                r["expPoints"] = round(exp_ppg * r["played"], 1)
                r["diff"] = round(r["points"] - r["expPoints"], 1)
            else:
                r["expPoints"] = r["diff"] = None
        season = data.get("season", {})
        out["leagues"][league] = {
            "season": int(season["startDate"][:4]) if season.get("startDate") else None,
            "matchday": season.get("currentMatchday"),
            "rows": rows,
        }
        unmatched = [r["team"] for r in rows if not r["clubId"]]
        print(f"{code}: {len(rows)} teams, matchday {season.get('currentMatchday')}, "
              f"unmatched {unmatched or 'none'}, incomplete squads "
              f"{[r['team'] for r in rows if r['clubId'] and not r['complete']] or 'none'}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, help="read <CODE>.json standings from this directory")
    ap.add_argument("--out", type=Path, default=DATA / "money_live.json")
    args = ap.parse_args()
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "")
    if not token and not args.fixture:
        print("FOOTBALL_DATA_TOKEN is not set; skipping live standings.")
        return 0
    out = build(token, args.fixture)
    # Only rewrite when the tables changed, so the daily job commits after matchdays, not every day.
    if args.out.exists():
        old = json.loads(args.out.read_text())
        if {k: v for k, v in old.items() if k != "fetched"} == {k: v for k, v in out.items() if k != "fetched"}:
            print("Standings unchanged; nothing to write.")
            return 0
    args.out.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
