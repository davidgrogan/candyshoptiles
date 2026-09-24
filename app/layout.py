"""Grid layouts: a sparse list of placed tiles, [{"r": row, "c": col,
"image_id": id}, ...].

The grid has no fixed size -- it's just the bounding box of whatever's
been placed, so three tiles in a row, a column, or an L-shape are all
valid. Gaps inside the bounding box are allowed (they're blank wall).
"""
import json

MAX_SPAN = 12  # rows or columns


class LayoutError(ValueError):
    pass


def parse_layout(raw, valid_image_ids):
    """Validate and normalize a layout from the browser (JSON string or
    already-decoded list). Drops tiles whose image no longer exists, keeps
    the last tile if two share a cell, and shifts everything so the
    top-left occupied row/column is 0. Raises LayoutError on garbage or an
    oversized grid."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except json.JSONDecodeError as exc:
            raise LayoutError("Layout isn't valid JSON.") from exc
    if not isinstance(raw, list):
        raise LayoutError("Layout must be a list.")

    cells = {}
    for item in raw:
        if not isinstance(item, dict):
            raise LayoutError("Each tile must be an object.")
        try:
            r, c, image_id = int(item["r"]), int(item["c"]), int(item["image_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LayoutError("Each tile needs integer r, c and image_id.") from exc
        if abs(r) > 1000 or abs(c) > 1000:
            raise LayoutError("Tile position out of range.")
        if image_id in valid_image_ids:
            cells[(r, c)] = image_id

    if not cells:
        return []
    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    out = [{"r": r - min_r, "c": c - min_c, "image_id": i} for (r, c), i in cells.items()]
    rows, cols = dimensions(out)
    if rows > MAX_SPAN or cols > MAX_SPAN:
        raise LayoutError(f"Grids can be at most {MAX_SPAN} tiles in each direction.")
    out.sort(key=lambda t: (t["r"], t["c"]))
    return out


def dimensions(layout):
    """(rows, cols) of a normalized layout's bounding box; (0, 0) if empty."""
    if not layout:
        return 0, 0
    return max(t["r"] for t in layout) + 1, max(t["c"] for t in layout) + 1


def dump_layout(layout):
    return json.dumps(layout, separators=(",", ":"))
