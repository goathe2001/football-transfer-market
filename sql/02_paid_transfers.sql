-- One row per paid transfer with a pre-transfer market value, enriched with the
-- buying/selling league, player age and position, and transfer-window timing.
--
-- Filters and why:
--   transfer_fee > 0        free transfers, loans and loan returns are all stored as 0
--                            and cannot be told apart, so only paid moves are analysed
--   market_value_in_eur > 0 needed for the premium (fee / market value)
--   season 12/13 onward     fees are sparsely recorded before then
--   transfer_date <= today  the table contains pre-booked future moves (e.g. loan returns)
WITH base AS (
    SELECT
        t.player_id,
        t.player_name,
        t.transfer_date,
        t.transfer_season,
        2000 + CAST(LEFT(t.transfer_season, 2) AS INT)            AS season_start,
        t.from_club_name,
        t.to_club_name,
        t.transfer_fee                                             AS fee,
        t.market_value_in_eur                                      AS market_value,
        LN(t.transfer_fee) - LN(t.market_value_in_eur)             AS log_premium,
        COALESCE(buy.domestic_competition_id, 'Other')             AS buy_league,
        COALESCE(sell.domestic_competition_id, 'Other')            AS sell_league,
        p.position,
        date_diff('day', p.date_of_birth, t.transfer_date) / 365.25 AS age,
        -- Final week before the usual deadline of each window.
        (   (month(t.transfer_date) = 8 AND day(t.transfer_date) >= 25)
         OR (month(t.transfer_date) = 9 AND day(t.transfer_date) <= 2)
         OR (month(t.transfer_date) = 1 AND day(t.transfer_date) >= 25)
         OR (month(t.transfer_date) = 2 AND day(t.transfer_date) <= 3) ) AS deadline_week,
        month(t.transfer_date) IN (1, 2)                           AS winter_window
    FROM transfers t
    JOIN players p USING (player_id)
    LEFT JOIN clubs buy  ON buy.club_id  = t.to_club_id
    LEFT JOIN clubs sell ON sell.club_id = t.from_club_id
    WHERE t.transfer_fee > 0
      AND t.market_value_in_eur > 0
      AND t.transfer_date <= current_date
      AND t.transfer_season NOT LIKE '9%'
      AND CAST(LEFT(t.transfer_season, 2) AS INT) >= 12
      AND p.position IN ('Attack', 'Midfield', 'Defender', 'Goalkeeper')
      AND p.date_of_birth IS NOT NULL
)
SELECT *,
       CASE WHEN buy_league  IN ('GB1','ES1','IT1','L1','FR1') THEN buy_league  ELSE 'Other' END AS buy_group,
       CASE WHEN sell_league IN ('GB1','ES1','IT1','L1','FR1') THEN sell_league ELSE 'Other' END AS sell_group,
       CASE WHEN age < 21 THEN 'U21'
            WHEN age < 24 THEN '21-23'
            WHEN age < 27 THEN '24-26'
            WHEN age < 30 THEN '27-29'
            ELSE '30+' END                                         AS age_band
FROM base
WHERE age BETWEEN 16 AND 40;
