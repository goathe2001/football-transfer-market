"""Step 9: live league tables and match predictions (run daily by GitHub Actions).

Fetches the current big-five standings and fixtures from football-data.org and matches each team to
its Transfermarkt club. Then:
  * money_live.json: actual points vs. points expected from preseason squad value (model from step 8).
  * match_predictions.json: replays this season's results through the Elo model from step 10 (ratings,
    parameters and outcome model fixed before the season), predicts the next matchday, and tracks the
    season's accuracy. Every past prediction uses only results available before that match.
Standard library only, so the daily job needs no database.

Environment
  FOOTBALL_DATA_TOKEN   free API key from https://www.football-data.org/client/register
                        (without it the script exits without changing anything)

Usage
  python analysis/09_live_standings.py                 # live API
  python analysis/09_live_standings.py --fixture DIR   # read <CODE>.json files from DIR instead (tests)

Writes dashboard/public/data/money_live.json and match_predictions.json.
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
API = "https://api.football-data.org/v4/competitions/{code}/{kind}"
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


_last_call = [0.0]


def fetch(code: str, token: str, fixture: Path | None, kind: str = "standings") -> dict:
    if fixture:
        name = f"{code}.json" if kind == "standings" else f"{code}_{kind}.json"
        return json.loads((fixture / name).read_text())
    wait = 7 - (time.time() - _last_call[0])  # free tier: 10 requests per minute
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    req = urllib.request.Request(API.format(code=code, kind=kind), headers={"X-Auth-Token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ------------------------------------------------------------------------------- predictions
def outcome_probs(o: dict, gap: float) -> list:
    """Ordered logit: rating gap (hundreds of Elo points) -> [P(home), P(draw), P(away)]."""
    sig = lambda x: 1 / (1 + math.exp(-x))
    p_away = sig(o["c1"] - o["beta"] * gap)
    p_le_draw = sig(o["c1"] + math.exp(o["logGap"]) - o["beta"] * gap)
    return [1 - p_le_draw, p_le_draw - p_away, p_away]


def rps(p: list, outcome: str) -> float:
    o = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[outcome]
    return 0.5 * ((p[0] - o[0]) ** 2 + (p[0] + p[1] - o[0] - o[1]) ** 2)


def margin_mult(gd: int) -> float:
    gd = abs(gd)
    return 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8


def predict_league(league: str, matches: list, team_club: dict, money_rows: list, state: dict) -> dict:
    """Season-start ratings, replay of finished matches, next-matchday predictions."""
    base, reg, H, K = state["base"], state["reg"], state["H"], state["K"]
    prev = {int(k): v["rating"] for k, v in state["ratings"].get(league, {}).items()}
    members = {c for c in team_club.values() if c is not None}
    leavers = [r for c, r in prev.items() if c not in members]
    newcomer = sum(leavers) / len(leavers) if leavers else base - 100
    # Relative squad value, same definition as the step-8 and step-10 models.
    complete = {r["clubId"]: r["value"] for r in money_rows if r["complete"] and r["value"]}
    mean_log = sum(math.log(v) for v in complete.values()) / len(complete) if complete else 0.0
    vp = state["valuePrior"]
    start = {}
    for team_id, club in team_club.items():
        r = base + (1 - reg) * (prev[club] - base) if club in prev else newcomer
        if vp["used"] and club in complete:
            r = (1 - vp["w"]) * r + vp["w"] * (base + vp["b"] * (math.log(complete[club]) - mean_log))
        start[team_id] = r
    R = dict(start)

    def name(t):
        return t.get("shortName") or t.get("name")

    played, upcoming = [], []
    for m in sorted(matches, key=lambda m: (m["utcDate"], m["id"])):
        h, a = m["homeTeam"], m["awayTeam"]
        for t in (h, a):
            R.setdefault(t["id"], newcomer)
            start.setdefault(t["id"], newcomer)
        ft = (m.get("score") or {}).get("fullTime") or {}
        gap = (R[h["id"]] + H - R[a["id"]]) / 100
        p = outcome_probs(state["ordered"], gap)
        if m["status"] == "FINISHED" and ft.get("home") is not None:
            hg, ag = ft["home"], ft["away"]
            outcome = "H" if hg > ag else "D" if hg == ag else "A"
            played.append({"date": m["utcDate"][:10], "md": m.get("matchday"), "home": name(h), "away": name(a),
                           "hg": hg, "ag": ag, "p": [round(x, 3) for x in p], "outcome": outcome,
                           "rps": round(rps(p, outcome), 4),
                           "fav": "HDA"[max(range(3), key=lambda k: p[k])] == outcome})
            exp_h = 1 / (1 + 10 ** (-(R[h["id"]] + H - R[a["id"]]) / 400))
            res = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
            g = margin_mult(hg - ag) if state["margin"] else 1.0
            R[h["id"]] += K * g * (res - exp_h)
            R[a["id"]] -= K * g * (res - exp_h)
        elif m["status"] in ("SCHEDULED", "TIMED"):
            upcoming.append({"date": m["utcDate"], "md": m.get("matchday"), "home": name(h), "away": name(a),
                             "hId": h["id"], "aId": a["id"]})
    # Predict the next matchday with current ratings.
    next_md = min((u["md"] for u in upcoming if u["md"] is not None), default=None)
    nxt = []
    for u in upcoming:
        if u["md"] == next_md:
            p = outcome_probs(state["ordered"], (R[u["hId"]] + H - R[u["aId"]]) / 100)
            nxt.append({"date": u["date"], "home": u["home"], "away": u["away"], "p": [round(x, 3) for x in p]})
    b = state["baseline"]
    n = len(played)
    names = {}
    for m in matches:
        for t in (m["homeTeam"], m["awayTeam"]):
            names[t["id"]] = name(t)
    return {
        "played": n,
        "rps": round(sum(x["rps"] for x in played) / n, 4) if n else None,
        "rpsBase": round(sum(rps(b, x["outcome"]) for x in played) / n, 4) if n else None,
        "favHit": round(sum(x["fav"] for x in played) / n, 3) if n else None,
        "nextMatchday": next_md,
        "next": nxt,
        "results": list(reversed(played)),
        "ratings": sorted(({"team": names.get(t, str(t)), "rating": round(r, 1), "change": round(r - start[t], 1)}
                           for t, r in R.items()), key=lambda x: -x["rating"]),
    }


def build(token: str, fixture: Path | None) -> tuple:
    history = json.loads((DATA / "money_history.json").read_text())
    state = json.loads((DATA / "elo_state.json").read_text())
    pre = json.loads((DATA / "preseason_live.json").read_text())
    model, min_players = history["model"], pre["minPlayers"]
    clubs = pre["clubs"]

    fetched = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    out = {"fetched": fetched, "valuesAsOf": pre["valuesAsOf"], "leagues": {}}
    pred = {"fetched": fetched, "leagues": {}}
    for code, league in COMPETITIONS.items():
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
        team_club = {t["team"]["id"]: (club["id"] if club else None) for t, (club, _) in zip(table, matches)}
        fixtures = fetch(code, token, fixture, "matches").get("matches", [])
        pred["leagues"][league] = predict_league(league, fixtures, team_club, rows, state)
        unmatched = [r["team"] for r in rows if not r["clubId"]]
        print(f"{code}: {len(rows)} teams, matchday {season.get('currentMatchday')}, "
              f"unmatched {unmatched or 'none'}, incomplete squads "
              f"{[r['team'] for r in rows if r['clubId'] and not r['complete']] or 'none'}; "
              f"{pred['leagues'][league]['played']} results replayed, next matchday "
              f"{pred['leagues'][league]['nextMatchday']} ({len(pred['leagues'][league]['next'])} fixtures)")
    lg = pred["leagues"].values()
    n = sum(x["played"] for x in lg)
    if n:
        r = sum(x["rps"] * x["played"] for x in lg if x["played"]) / n
        rb = sum(x["rpsBase"] * x["played"] for x in lg if x["played"]) / n
        fav = sum(x["favHit"] * x["played"] for x in lg if x["played"]) / n
        pred["overall"] = {"played": n, "rps": round(r, 4), "rpsBase": round(rb, 4),
                           "skill": round(1 - r / rb, 4), "favHit": round(fav, 3)}
    else:
        pred["overall"] = {"played": 0, "rps": None, "rpsBase": None, "skill": None, "favHit": None}
    return out, pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, help="read <CODE>.json standings from this directory")
    ap.add_argument("--out", type=Path, default=DATA / "money_live.json")
    ap.add_argument("--pred-out", type=Path, default=DATA / "match_predictions.json")
    args = ap.parse_args()
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "")
    if not token and not args.fixture:
        print("FOOTBALL_DATA_TOKEN is not set; skipping live standings.")
        return 0
    money, pred = build(token, args.fixture)
    # Only rewrite a file when its content changed (ignoring the fetch time), so the daily job
    # commits after matchdays, not every day.
    for path, obj in ((args.out, money), (args.pred_out, pred)):
        if path.exists():
            old = json.loads(path.read_text())
            if {k: v for k, v in old.items() if k != "fetched"} == {k: v for k, v in obj.items() if k != "fetched"}:
                print(f"{path.name} unchanged.")
                continue
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
