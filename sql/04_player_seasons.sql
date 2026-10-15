-- One row per player per season (season = July to June, labelled by its start year) with
-- performance features and the market value at the end of that season and the next one.
--
-- Performance comes from the player's domestic-league games; the "main" league and club are the
-- ones where he played the most minutes. Club strength is that club's points per game and goal
-- difference per game in the same league season. Market value at season end = last valuation
-- between January and July of the season's second calendar year.
WITH app AS (
    SELECT a.*,
           CASE WHEN month(a.date) >= 7 THEN year(a.date) ELSE year(a.date) - 1 END AS season
    FROM appearances a
),
leagues AS (
    SELECT competition_id FROM competitions WHERE type = 'domestic_league'
),
by_league AS (
    SELECT player_id, season, competition_id AS league, player_club_id AS club_id,
           SUM(minutes_played) AS minutes, COUNT(*) AS apps,
           SUM(goals) AS goals, SUM(assists) AS assists, SUM(yellow_cards) AS yellows
    FROM app
    WHERE competition_id IN (SELECT competition_id FROM leagues)
    GROUP BY ALL
),
main_club AS (
    -- League and club where the player played most; explicit tie-breaks keep this deterministic.
    SELECT player_id, season, league, club_id
    FROM by_league
    QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id, season
                               ORDER BY minutes DESC, apps DESC, league, club_id) = 1
),
league_season AS (
    SELECT b.player_id, b.season, m.league, m.club_id,
           SUM(b.minutes) AS league_minutes, SUM(b.apps) AS league_apps,
           SUM(b.goals) AS goals, SUM(b.assists) AS assists, SUM(b.yellows) AS yellows
    FROM by_league b
    JOIN main_club m USING (player_id, season)
    GROUP BY ALL
),
europe AS (
    SELECT player_id, season, SUM(minutes_played) AS euro_minutes,
           SUM(goals + assists) AS euro_goal_contrib
    FROM app
    WHERE competition_id IN ('CL', 'EL', 'UCOL')
    GROUP BY ALL
),
club_strength AS (
    SELECT cg.club_id, g.competition_id AS league,
           CASE WHEN month(g.date) >= 7 THEN year(g.date) ELSE year(g.date) - 1 END AS season,
           COUNT(*) AS club_games,
           AVG(CASE WHEN cg.own_goals > cg.opponent_goals THEN 3
                    WHEN cg.own_goals = cg.opponent_goals THEN 1 ELSE 0 END) AS club_ppg,
           AVG(cg.own_goals - cg.opponent_goals) AS club_gd
    FROM club_games cg
    JOIN games g USING (game_id)
    WHERE g.competition_id IN (SELECT competition_id FROM leagues)
    GROUP BY ALL
),
season_end_value AS (
    SELECT player_id, year(date) - 1 AS season, market_value_in_eur AS value
    FROM player_valuations
    WHERE month(date) <= 7 AND market_value_in_eur > 0
    QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id, year(date)
                               ORDER BY date DESC, market_value_in_eur DESC) = 1
)
SELECT ls.*,
       p.name, p.position, p.sub_position, p.foot, p.height_in_cm,
       p.contract_expiration_date, p.current_club_name,
       c.name AS club_name,
       (ls.season + 1) - year(p.date_of_birth)
         - CASE WHEN month(p.date_of_birth) > 6 THEN 1 ELSE 0 END AS age,  -- age on 30 June
       COALESCE(e.euro_minutes, 0)      AS euro_minutes,
       COALESCE(e.euro_goal_contrib, 0) AS euro_goal_contrib,
       cs.club_games, cs.club_ppg, cs.club_gd,
       v0.value AS value,
       v1.value AS value_next
FROM league_season ls
JOIN players p USING (player_id)
LEFT JOIN clubs c ON c.club_id = ls.club_id
LEFT JOIN europe e USING (player_id, season)
LEFT JOIN club_strength cs ON cs.club_id = ls.club_id AND cs.league = ls.league AND cs.season = ls.season
LEFT JOIN season_end_value v0 ON v0.player_id = ls.player_id AND v0.season = ls.season
LEFT JOIN season_end_value v1 ON v1.player_id = ls.player_id AND v1.season = ls.season + 1
WHERE ls.league_minutes >= 900
  AND p.position IN ('Attack', 'Midfield', 'Defender', 'Goalkeeper')
  AND p.date_of_birth IS NOT NULL;
