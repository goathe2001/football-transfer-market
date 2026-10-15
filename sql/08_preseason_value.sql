-- Preseason squad value and final league record for every big-five club-season, 2018/19-2025/26.
-- (Valuation coverage before 2018 is too sparse: some top clubs' squads are undercounted by half.)
--
-- Preseason squad: each player's last market valuation on or before 31 August of the season's
-- first year (and within the previous 12 months); the club recorded on that valuation is his club.
-- This uses only information available before the season, so there is no hindsight about who
-- ended up playing. Ties on date are broken by value so the result is deterministic.
--
-- Final record: points (3/1/0), games and goal difference computed from that season's league games.
WITH seasons AS (
    SELECT DISTINCT competition_id AS league, CAST(season AS INT) AS season
    FROM games
    WHERE competition_id IN ('GB1', 'ES1', 'IT1', 'L1', 'FR1')
      AND CAST(season AS INT) BETWEEN 2018 AND 2025
),
results AS (
    SELECT g.competition_id AS league, CAST(g.season AS INT) AS season, x.club_id,
           COUNT(*) AS played,
           SUM(CASE WHEN x.gf > x.ga THEN 3 WHEN x.gf = x.ga THEN 1 ELSE 0 END) AS points,
           SUM(x.gf - x.ga) AS goal_diff
    FROM games g,
         LATERAL (VALUES (g.home_club_id, g.home_club_goals, g.away_club_goals),
                         (g.away_club_id, g.away_club_goals, g.home_club_goals)) AS x(club_id, gf, ga)
    WHERE g.competition_id IN ('GB1', 'ES1', 'IT1', 'L1', 'FR1')
      AND CAST(g.season AS INT) BETWEEN 2018 AND 2025
      AND g.home_club_goals IS NOT NULL
    GROUP BY ALL
),
preseason AS (
    SELECT s.season, v.player_id, v.current_club_id AS club_id, v.market_value_in_eur AS value
    FROM (SELECT DISTINCT season FROM seasons) s
    JOIN player_valuations v
      ON v.date <= make_date(s.season, 8, 31)
     AND v.date >  make_date(s.season - 1, 8, 31)
    WHERE v.market_value_in_eur > 0
    QUALIFY ROW_NUMBER() OVER (PARTITION BY s.season, v.player_id
                               ORDER BY v.date DESC, v.market_value_in_eur DESC) = 1
),
squad AS (
    SELECT season, club_id, SUM(value) AS squad_value, COUNT(*) AS squad_players
    FROM preseason
    GROUP BY ALL
)
SELECT r.league, r.season, r.club_id, c.name AS club,
       r.played, r.points, r.goal_diff,
       r.points * 1.0 / r.played AS ppg,
       COALESCE(q.squad_value, 0) AS squad_value,
       COALESCE(q.squad_players, 0) AS squad_players
FROM results r
LEFT JOIN squad q USING (season, club_id)
LEFT JOIN clubs c ON c.club_id = r.club_id
ORDER BY r.league, r.season, r.points DESC, r.goal_diff DESC, r.club_id;
