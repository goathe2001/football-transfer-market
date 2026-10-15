# European Football Transfer Market Analysis

Is the football transfer market rational? This project uses Transfermarkt data to study how player
market values evolve, whether clubs pay systematic premiums over market value, and how much a
World Cup moves a player's valuation.

> Work in progress. Findings are added to each section as the analysis is completed.

## Questions

1. **Age curves.** At what age does market value peak for each position, and how fast does it decline?
2. **Transfer premiums.** Do clubs pay more than market value, and does the premium depend on the
   buying league, selling league, player age, position, or transfer-window timing?
3. **Tournament effect.** Does scoring or assisting at a World Cup, Euro or Copa América raise a
   player's valuation, and does the jump last? (7 tournaments, 2014–2024)
4. **Undervalued players.** Which players are valued well below what their performance predicts,
   and does being undervalued predict future value growth?

## Data

[transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) by David Cariboo:
a cleaned, weekly-refreshed export of Transfermarkt (players, valuations, transfers, appearances,
games). Downloaded as a single DuckDB file; not committed to this repo.

## Findings so far

### 1. Age curves: the naive curve hides how fast value collapses after 30

![Age curves](figures/01_age_curves.png)

Market value is estimated two ways. The **cross-sectional median** compares different players at
each age; it is biased by survivorship, because weaker players drop out of the data as they age and
the ones left at 32 are unusually good. The **delta method** averages each player's own year-over-year
change in log value and chains those changes, so dropouts no longer distort the shape.

| Position   | Peak age | Value kept at 30 (naive / delta) | Value kept at 32 (naive / delta) |
|------------|---------:|---------------------------------:|---------------------------------:|
| Attack     | 26       | 88% / 66%                        | 62% / **35%**                    |
| Midfield   | 27       | 94% / 71%                        | 62% / **37%**                    |
| Defender   | 27       | 87% / 74%                        | 60% / **41%**                    |
| Goalkeeper | 28       | 100% / 92%                       | 85% / **69%**                    |

Outfield players peak at 26–27 and goalkeepers about two years later. The peak age barely moves
between methods; the decline does. The naive curve says a 32-year-old attacker keeps 62% of his
peak value, while the within-player estimate is 35%. For a club, that gap is the difference between
a sensible contract extension and an expensive one.

### 2. Transfer premiums: the Premier League pays roughly double

![Transfer premiums](figures/02_transfer_premium.png)

Across 15,983 paid transfers (2012/13 onward), the median fee is 7% **below** the pre-transfer
market value, and only 42% of deals are paid above it. The overall market is not systematically
overpaying. Who is buying matters far more:

- **Premier League clubs** pay a median 33% over market value, and 70% of their purchases are above
  it. Holding seller, age, position, player value, timing and season constant, an English buyer pays
  about **+97%** relative to a club outside the big five leagues; Serie A and Ligue 1 buyers about
  +47–50%, LaLiga +25%, Bundesliga +13%.
- The English premium peaked at about +67% around 2017–2019 and has fallen to roughly +20–30% since.
- **Youth costs extra.** Under-21 players go for about +80% over market value relative to 24–26
  year olds, and 21–23 year olds about +22%; players over 30 sell at about −24%. Buyers are paying for
  potential that the market value has not yet priced in.
- **Deadline week** deals carry about +13%; winter-window deals about −6%.
- More expensive players carry a smaller premium (−9% per log unit of market value), consistent with
  market values for cheap players being noisier.

Model: OLS on log(fee / market value), standard errors clustered by buying club, season fixed
effects; R² = 0.17. Coefficients are associations, not causal effects.

### 3. Tournament effect: a goal or assist is worth about +12–15%, and it sticks

![Tournament effect](figures/03_world_cup_effect.png)

Event study across 7 tournaments (World Cups 2014/2018/2022, Euros 2016/2021/2024, Copa América
2024): 12,511 international-level player-tournaments, 662 of them with at least one goal or assist.
Each scorer or assister is compared with peers from the **same tournament, position, age band and
pre-tournament value quintile**, tracking every valuation from a year before kickoff to a year after
the final.

- **Pre-trend check.** With value, age and position matching alone, future scorers were already
  rising about 5–8% faster in the year before the tournament: they were in form, so a naive
  comparison would credit the tournament with growth that was already happening. Adding
  **pre-tournament momentum** to the matching removes most of this (the 6–12 month pre-period
  differences become statistically indistinguishable from zero); a small run-up of about 4% remains
  in the final six months before kickoff.
- **Effect.** With that correction, scorers and assisters gain an extra **+18%** in the first
  quarter after the final, settling at **+12–13%** after six months and **+15%** after a year. The
  bump does not fade within twelve months.
- **Dose response.** One or two goal contributions are worth about +10–13%; three or more about
  **+22–24%**.

Model: for each quarter of event time, OLS of the log change from the last pre-tournament value on a
treatment indicator, with matching-cell fixed effects and standard errors clustered by player.

### 4. Undervalued players: the model's "bargains" really do appreciate

![Undervalued players](figures/04_undervalued.png)

A gradient-boosting model predicts each player's season-end market value from that season's
performance: league minutes and share of club minutes, goals and assists per 90, European minutes and
output, club points and goal difference per game, league, age, position, height and foot. It is
trained on 50,113 player-seasons (at least 900 league minutes, 2012/13–2025/26), with the target
defined relative to each season's median so market inflation does not leak in.

- **Walk-forward validation.** Each season from 2018/19 is predicted by a model trained only on
  earlier seasons. Out-of-sample R² is **0.82–0.87** (linear baseline 0.80–0.85); the median
  prediction is within about 45% of the actual value.
- **Backtest.** If the residual (actual minus predicted) captures real mispricing, undervalued
  players should catch up. They do: across 23,348 player-seasons, the most undervalued decile gained
  **+16%** relative to the market over the following year and the most overvalued decile lost about
  3%, with a monotone pattern in between. The gap holds within every age band (≤23: +35 points,
  24–27: +28, 28+: +18 between the bottom and top fifths), so it is not just young players growing.
- **2025/26 scouting list** (`outputs/04_undervalued_2025_26.csv`): players aged 26 or under with
  at least 1,500 league minutes and a value of at least EUR 1m, ranked by how far their market value
  sits below the model's estimate. Russian and Ukrainian league players are left off the list: their
  values have been structurally lower since 2022, a break the model cannot learn from earlier seasons,
  so they would appear as false bargains. Excluding them leaves the backtest unchanged (decile 1
  +16.6%, decile 10 −2.7%).

The list is a starting point for scouting, not a verdict. The model sees only goals, assists, minutes
and team context, so it cannot judge defensive quality, injuries or contract situations.

## Run it

```bash
pip install -r requirements.txt
bash data/download.sh              # ~ downloads data/transfermarkt.duckdb
python analysis/00_inspect.py      # tables, columns, fee coverage
python analysis/01_age_curves.py   # add --big5 for top-5 leagues only
python analysis/02_transfer_premium.py
python analysis/03_world_cup_effect.py
python analysis/04_undervalued.py
```

The main SQL lives in `sql/` (`02_paid_transfers.sql`, `03_tournament_panel.sql`,
`04_player_seasons.sql`).

## Repository layout

```
data/       download script (database itself is git-ignored)
analysis/   one script per question, numbered in order
figures/    charts produced by the scripts
outputs/    CSV tables produced by the scripts
dashboard/  interactive React dashboard (planned)
```

## Limitations

- Transfermarkt market values are community estimates, not observed prices.
- Free transfers, loans and loan returns are all stored with a fee of 0 and cannot be separated, so
  the premium analysis covers paid transfers only. Fees are sparse before 2012/13.
- About 6% of paid transfers have a fee exactly equal to market value, likely because Transfermarkt
  editors anchor valuations on reported fees. This pulls small-group medians toward 0%.
- Contract length at the time of a transfer is not in the data (only each player's current
  contract), so its effect on fees cannot be estimated here.
- "Other leagues" mixes many markets, including ones outside the dataset's tracked leagues.
- Tournament squads and minutes are only recorded for 2026, so earlier tournaments identify
  players by goal events (scorers and assisters) and use international caps (current snapshot) to
  define the comparison pool. The control group therefore includes some players who were not at the
  tournament, and the estimate combines "played well" with "was selected and played".
- The 2026 World Cup cannot be analysed yet: valuations in this snapshot end on 2026-06-12.
- Performance data is limited to goals, assists, minutes and cards (no expected-goals data).

## Data credit

Data from Transfermarkt via [transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets).
