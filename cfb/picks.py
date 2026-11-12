"""Our picks: which side, how strong (the tier), and the best number to bet it at.

The worker records a pick for every upcoming game after each odds snapshot (pick_log),
so we can grade what we actually would have bet, at the price we could actually get.
"""

from datetime import datetime, timezone

from psycopg.rows import dict_row

from cfb.db import connect
from cfb.model import MODEL_VERSION

PLAY_GAP = 3.0          # points off the market before a side is worth a bet
TOTAL_GAP = 3.0         # same for totals (shown as info only)
MOVE_MIN = 0.5      # a line "moved" if it changed by at least this much since the open

# Upcoming games:  our line (overrides included), the CFBD open, and the market right now
UPCOMING_SQL = """
WITH adjustments AS (
    SELECT o.game_id,
        COALESCE(sum(o.points) FILTER (WHERE o.team_id = g.home_id), 0) AS home_adj,
        COALESCE(sum(o.points) FILTER (WHERE o.team_id = g.away_id), 0) AS away_adj
        FROM overrides o
        JOIN games g ON g.id = o.game_id
        WHERE o.active
        GROUP BY o.game_id
),
opening AS (
    SELECT game_id, avg(spread_open) AS open_spread
    FROM lines
    GROUP BY game_id
)
SELECT g.id AS game_id,
    p.spread + COALESCE(adj.away_adj, 0) - COALESCE(adj.home_adj, 0) AS spread,
    p.total + COALESCE(adj.home_adj, 0) + COALESCE(adj.away_adj, 0) AS total,
    op.open_spread,
    mn.books,
    mn.spread AS market_spread,
    mn.total AS market_total,
    mn.best_home_book, mn.best_home_spread, mn.best_home_price,
    mn.best_away_book, mn.best_away_spread, mn.best_away_price,
    mn.best_over_book, mn.best_over_total, mn.best_over_price,
    mn.best_under_book, mn.best_under_total, mn.best_under_price
FROM games g
JOIN predictions p ON p.game_id = g.id
                   AND p.model_version = %(version)s
                   AND NOT p.is_backtest
JOIN market_now mn ON mn.game_id = g.id
LEFT JOIN adjustments adj ON adj.game_id = g.id
LEFT JOIN opening op ON op.game_id = g.id
WHERE g.league = 'cfb'
  AND g.start_time > now()
"""


def make_pick(g):
    """Tier, side and best number for one game.
    
    g needs: spread, total (ours), market_spread, market_total, open_spread, and the 
    best_home_/best_away_/best_over_/best_under_ book, spread or total, and price.

    play:    we differ from the current line by 3+ and the market isn't moving against us
    caution:    3+ apart, but the line has moved the other way since it opened
    pass:       under 3 points apart
    PICK_RATES_SQL (cfb/web/main.py) uses the same rule for the backtest rates: change both together.
    """
    pick = {"tier": None, "side": None, "gap": None, "moved": None, "toward": None,
            "bet_spread": None, "bet_price": None, "bet_book": None,
            "total_side": None, "total_gap": None, "bet_total": None, "total_price": None, "total_book": None}

    if g.get("market_spread") is not None:
        ours = float(g["spread"])
        market = float(g["market_spread"])
        diff = ours - market        # negative = we like the home team more than the market does
        pick["gap"] = abs(diff)
        if diff < 0:
            pick["side"] = "home"
        elif diff > 0:
            pick["side"] = "away"

        against = False
        if g.get("open_spread") is not None:
            opened = float(g["open_spread"])
            move = market - opened
            toward = (move < 0 and ours < opened) or (move > 0 and ours > opened)
            pick["moved"] = abs(move)
            pick["toward"] = toward
            against = abs(move) >= MOVE_MIN and not toward
        
        if abs(diff) < PLAY_GAP:
            pick["tier"] = "pass"
        elif against:
            pick["tier"] = "caution"
        else:
            pick["tier"] = "play"
        
        if pick["side"] is not None:
            prefix = "best_" + pick["side"] + "_"
            pick["bet_spread"] = g.get(prefix + "spread")
            pick["bet_price"] = g.get(prefix + "price")
            pick["bet_book"] = g.get(prefix + "book")
    
    if g.get("market_total") is not None:
        tdiff = float(g["total"]) - float(g["market_total"])
        pick["total_gap"] = abs(tdiff)
        if abs(tdiff) >= TOTAL_GAP:
            pick["total_side"] = "over" if tdiff > 0 else "under"
            prefix = "best_" + pick["total_side"] + "_"
            pick["bet_total"] = g.get(prefix + "total")
            pick["total_price"] = g.get(prefix + "price")
            pick["total_book"] = g.get(prefix + "book")

    return pick


def record_picks():
    """Save our current pick for every game that hasn't kicked off (run after each odds snapshot)."""
    recorded_at = datetime.now(timezone.utc)
    saved = 0
    with connect() as conn:
        conn.row_factory = dict_row
        games = conn.execute(UPCOMING_SQL, {"version": MODEL_VERSION}).fetchall()
        for g in games:
            pick = make_pick(g)
            if pick["tier"] is None:
                continue        # no market line yet
            conn.execute(
                """
                INSERT INTO pick_log (game_id, model_version, recorded_at,
                                      our_spread, our_total, market_spread, market_total,
                                      open_spread, books, tier, side,
                                      bet_spread, bet_price, bet_book,
                                      total_side, bet_total, total_price, total_book)
                VALUES (%(game_id)s, %(version)s, %(recorded_at)s,
                        %(spread)s, %(total)s, %(market_spread)s, %(market_total)s,
                        %(open_spread)s, %(books)s, %(tier)s, %(side)s,
                        %(bet_spread)s, %(bet_price)s, %(bet_book)s,
                        %(total_side)s, %(bet_total)s, %(total_price)s, %(total_book)s)
                ON CONFLICT (game_id, model_version, recorded_at) DO NOTHING
                """,
                {**g, **pick, "version": MODEL_VERSION, "recorded_at": recorded_at},
            )
            saved += 1
    print(f"picks recorded: {saved} games")
    return saved
