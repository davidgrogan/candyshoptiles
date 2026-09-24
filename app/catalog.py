"""Helpers shared by the public and admin routes: the image palette the
designer JS gets, and turning a stored layout into renderable cells."""
from flask import url_for

from app.images import image_url
from app.layout import DEFAULT_SPACING_IN, MAX_SPACING_IN, SPACING_STEP_IN, dimensions
from app.models import ArtImage, Category
from app.pricing import pricing_config


def palette(include_hidden=False):
    query = ArtImage.query
    if not include_hidden:
        query = query.filter(ArtImage.is_active.is_(True))
    images = query.order_by(ArtImage.sort_order, ArtImage.id).all()
    return [
        {
            "id": img.id,
            "title": img.title,
            "thumb": image_url(img.filename, "thumb"),
            "full": image_url(img.filename, "full"),
            "categories": [c.id for c in img.categories],
        }
        for img in images
    ]


def categories_for(images):
    used = {cid for img in images for cid in img["categories"]}
    return [
        {"id": c.id, "name": c.name}
        for c in Category.query.order_by(Category.sort_order, Category.name).all()
        if c.id in used
    ]


def designer_config(initial_layout=None, mode="customer", include_hidden=False, initial_spacing=None, **extra):
    images = palette(include_hidden=include_hidden)
    config = {
        "mode": mode,
        "images": images,
        "categories": categories_for(images),
        "pricing": pricing_config(),
        "initialLayout": initial_layout,
        "initialSpacing": initial_spacing,
        "spacing": {"default": DEFAULT_SPACING_IN, "max": MAX_SPACING_IN, "step": SPACING_STEP_IN},
        "urls": {"share": url_for("main.save_design")},
    }
    config.update(extra)
    return config


def image_ids(include_hidden=True):
    query = ArtImage.query.with_entities(ArtImage.id)
    if not include_hidden:
        query = query.filter(ArtImage.is_active.is_(True))
    return {row.id for row in query}


def resolve_cells(layout):
    """Attach title/filename to each tile of a live layout (sample sets,
    shared designs), skipping tiles whose image has since been deleted.
    Order snapshots already carry title/filename and don't need this."""
    ids = {t["image_id"] for t in layout}
    found = {img.id: img for img in ArtImage.query.filter(ArtImage.id.in_(ids)).all()} if ids else {}
    return [
        {**t, "title": found[t["image_id"]].title, "filename": found[t["image_id"]].filename}
        for t in layout
        if t["image_id"] in found
    ]


def grid_info(cells, spacing=DEFAULT_SPACING_IN):
    """Bounding box plus real-world size. Overall size counts the gaps
    between tiles, not around the outside."""
    rows, cols = dimensions(cells)
    cfg = pricing_config()
    return {
        "rows": rows,
        "cols": cols,
        "spacing": spacing,
        "tile_w": cfg["tileWidthIn"],
        "tile_h": cfg["tileHeightIn"],
        "width_in": cols * cfg["tileWidthIn"] + max(cols - 1, 0) * spacing,
        "height_in": rows * cfg["tileHeightIn"] + max(rows - 1, 0) * spacing,
    }
