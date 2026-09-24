"""Prices and tile dimensions -- the one place to change them.

The designer's running total (static/designer.js) gets these same numbers
via pricing_config(), and every order total is recomputed here on the
server rather than trusted from the browser.
"""

SAMPLE_TILE_CENTS = 2900   # one per order
SINGLE_TILE_CENTS = 4900   # an order of exactly one tile
MULTI_TILE_CENTS = 3900    # each, when ordering two or more

TILE_WIDTH_IN = 8
TILE_HEIGHT_IN = 10


def tile_unit_cents(tile_count):
    return SINGLE_TILE_CENTS if tile_count == 1 else MULTI_TILE_CENTS


def quote(tile_count, include_sample=False):
    unit = tile_unit_cents(tile_count)
    tiles = unit * tile_count
    sample = SAMPLE_TILE_CENTS if include_sample else 0
    return {
        "tile_count": tile_count,
        "unit_cents": unit,
        "tiles_cents": tiles,
        "sample_cents": sample,
        "total_cents": tiles + sample,
    }


def money(cents):
    dollars, rem = divmod(int(cents), 100)
    return f"${dollars:,}" if rem == 0 else f"${dollars:,}.{rem:02d}"


def pricing_config():
    return {
        "sampleCents": SAMPLE_TILE_CENTS,
        "singleCents": SINGLE_TILE_CENTS,
        "multiCents": MULTI_TILE_CENTS,
        "tileWidthIn": TILE_WIDTH_IN,
        "tileHeightIn": TILE_HEIGHT_IN,
    }
