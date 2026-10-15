-- Valuation panel around major tournaments, for an event study of goal contributions.
--
-- Tournaments: World Cups 2014/2018/2022, Euros 2016/2020(played 2021)/2024, Copa America 2024.
-- The 2026 World Cup is excluded: valuations in this snapshot end on 2026-06-12.
--
-- Eligible players for each tournament (treated and controls alike):
--   * a market value recorded in the 12 months before kickoff, of at least EUR 1m
--   * at least 10 international caps (current snapshot; a proxy for international-level players,
--     because squads are not recorded for these tournaments)
--   * aged 18-34 at kickoff, known position
-- Treated = at least one goal or assist at the tournament (own goals and won penalties excluded).

WITH tournament_dates AS (
    SELECT competition_id, season, MIN(date) AS t_start, MAX(date) AS t_end
    FROM games
    WHERE competition_id IN ('FIWC', 'EURO', 'COPA')
      AND YEAR(date) BETWEEN 2014 AND 2025
    GROUP BY competition_id, season
),
tournaments AS (
    SELECT *,
           CASE competition_id WHEN 'FIWC' THEN 'World Cup' WHEN 'EURO' THEN 'Euro' ELSE 'Copa America' END
             || ' ' || YEAR(t_end) AS tournament
    FROM tournament_dates
),
goal_events AS (
    SELECT t.tournament, e.player_id AS scorer_id, e.player_assist_id AS assist_id, e.description
    FROM game_events e
    JOIN games g ON CAST(e.game_id AS VARCHAR) = g.game_id
    JOIN tournaments t ON t.competition_id = g.competition_id AND t.season = g.season
    WHERE e.type = 'Goals'
),
contributions AS (
    SELECT tournament, player_id, SUM(goals) AS goals, SUM(assists) AS assists
    FROM (
        SELECT tournament, scorer_id AS player_id, 1 AS goals, 0 AS assists
        FROM goal_events
        WHERE description NOT ILIKE '%own%'
        UNION ALL
        SELECT tournament, assist_id, 0, 1
        FROM goal_events
        WHERE assist_id IS NOT NULL
          AND assist_id <> scorer_id
          AND description NOT ILIKE '%fouled player%'
          AND description NOT ILIKE '%own%'
    )
    GROUP BY ALL
),
baseline AS (
    -- Last valuation before kickoff (within 12 months); ties on date broken by value.
    SELECT t.tournament, t.t_start, t.t_end, v.player_id,
           v.market_value_in_eur AS pre_value, v.date AS pre_date
    FROM tournaments t
    JOIN player_valuations v
      ON v.date < t.t_start AND v.date >= t.t_start - INTERVAL 12 MONTH
    QUALIFY ROW_NUMBER() OVER (PARTITION BY t.tournament, v.player_id
                               ORDER BY v.date DESC, v.market_value_in_eur DESC) = 1
),
eligible AS (
    SELECT b.*, p.position,
           date_diff('day', p.date_of_birth, b.t_start) / 365.25 AS age,
           COALESCE(c.goals, 0) AS goals,
           COALESCE(c.assists, 0) AS assists,
           COALESCE(c.goals, 0) + COALESCE(c.assists, 0) AS contributions
    FROM baseline b
    JOIN players p USING (player_id)
    LEFT JOIN contributions c USING (tournament, player_id)
    WHERE b.pre_value >= 1e6
      AND p.international_caps >= 10
      AND p.position IN ('Attack', 'Midfield', 'Defender', 'Goalkeeper')
      AND date_diff('day', p.date_of_birth, b.t_start) / 365.25 BETWEEN 18 AND 34
)
SELECT e.tournament, e.player_id, e.position, e.age, e.pre_value, e.goals, e.assists,
       e.contributions, v.date,
       LN(v.market_value_in_eur) - LN(e.pre_value) AS log_change,
       -- Event time in quarters: negative before kickoff, positive after the final, 0 during.
       CASE WHEN v.date < e.t_start THEN -CAST(CEIL(date_diff('day', v.date, e.t_start) / 91.3) AS INT)
            WHEN v.date > e.t_end   THEN  CAST(CEIL(date_diff('day', e.t_end, v.date) / 91.3) AS INT)
            ELSE 0 END AS quarter
FROM eligible e
JOIN player_valuations v
  ON v.player_id = e.player_id
 AND v.date BETWEEN e.t_start - INTERVAL 12 MONTH AND e.t_end + INTERVAL 12 MONTH
 AND v.market_value_in_eur > 0;
