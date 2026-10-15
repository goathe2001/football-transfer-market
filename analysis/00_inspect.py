"""Step 0: list every table, its row count and columns, and check the columns later steps rely on."""
from common import columns, connect

# Columns the analysis plans to use. Anything missing here must be fixed before steps 1-4.
EXPECTED = {
    "players": {"player_id", "name", "date_of_birth", "position", "market_value_in_eur",
                "contract_expiration_date"},
    "player_valuations": {"player_id", "date", "market_value_in_eur",
                          "player_club_domestic_competition_id"},
    "transfers": {"player_id", "transfer_date", "transfer_season", "from_club_id", "to_club_id",
                  "transfer_fee", "market_value_in_eur"},
    "appearances": {"player_id", "game_id", "date", "minutes_played", "goals", "assists"},
}


def main() -> None:
    con = connect()
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    print(f"{len(tables)} tables\n")
    for t in tables:
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"== {t}  ({n:,} rows)")
        print("   " + ", ".join(sorted(columns(con, t))))

    print("\nColumn check")
    for t, needed in EXPECTED.items():
        if t not in tables:
            print(f"  [MISSING TABLE] {t}")
            continue
        missing = needed - columns(con, t)
        print(f"  {'OK ' if not missing else 'FIX'} {t}" + (f": missing {sorted(missing)}" if missing else ""))

    if "transfers" in tables:
        print("\nTransfer fee coverage (how many transfers have a usable fee):")
        print(con.execute("""
            SELECT COUNT(*)                                        AS transfers,
                   COUNT(*) FILTER (WHERE transfer_fee > 0)        AS paid_fee,
                   COUNT(*) FILTER (WHERE transfer_fee = 0)        AS free_or_zero,
                   COUNT(*) FILTER (WHERE transfer_fee IS NULL)    AS fee_unknown,
                   MIN(transfer_date) AS first_date, MAX(transfer_date) AS last_date
            FROM transfers
        """).df().to_string(index=False))


if __name__ == "__main__":
    main()
