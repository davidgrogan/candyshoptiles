"""Order requests. No payment is taken on the site: the customer sends
their grid plus contact/shipping details, you get an email, and you
follow up with an invoice. The total is always recomputed here from the
layout -- nothing price-related is read from the form."""
import re
import secrets

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.catalog import grid_info, image_ids, palette, resolve_cells
from app.layout import LayoutError, dump_layout, parse_layout
from app.models import ArtImage, OrderRequest, db
from app.notify import send_order_notification
from app.pricing import SAMPLE_TILE_CENTS, quote

bp = Blueprint("orders", __name__, url_prefix="/order")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FIELD_LIMITS = {"name": 200, "email": 254, "phone": 50, "address": 2000, "notes": 4000}


def _layout_from_form():
    try:
        return parse_layout(request.form.get("layout", "[]"), image_ids(include_hidden=True))
    except LayoutError:
        abort(400, description="That design couldn't be read -- please go back and try again.")


def _render_form(layout, form=None, errors=None):
    cells = resolve_cells(layout)
    sample_choices = palette()
    default_sample = cells[0]["image_id"] if cells else (sample_choices[0]["id"] if sample_choices else None)
    return render_template(
        "order_form.html",
        cells=cells,
        grid=grid_info(cells),
        layout_json=dump_layout(layout),
        tiles_quote=quote(len(cells)),
        sample_cents=SAMPLE_TILE_CENTS,
        sample_choices=sample_choices,
        default_sample=default_sample,
        form=form or {},
        errors=errors or {},
    ), (400 if errors else 200)


@bp.route("/start", methods=["GET", "POST"])
def start():
    """POST from the designer or a sample set carries the grid; a plain GET
    is the "just order a sample tile" path with an empty grid."""
    layout = _layout_from_form() if request.method == "POST" else []
    form = {"include_sample": "1"} if not layout else {}
    return _render_form(layout, form=form)


@bp.route("", methods=["POST"])
def submit():
    layout = _layout_from_form()
    form = {k: (request.form.get(k) or "").strip() for k in FIELD_LIMITS}
    form["include_sample"] = request.form.get("include_sample", "")
    form["sample_image_id"] = request.form.get("sample_image_id", "")

    # Honeypot: a field real people never see. Bots that fill it get the
    # normal-looking thank-you page and nothing is saved.
    if request.form.get("website"):
        return redirect(url_for("orders.thanks", token="received"))

    errors = {}
    if not form["name"]:
        errors["name"] = "Please enter your name."
    if not EMAIL_RE.match(form["email"]):
        errors["email"] = "Please enter a valid email address."
    if not form["address"]:
        errors["address"] = "Please enter a shipping address."
    for key, limit in FIELD_LIMITS.items():
        if len(form[key]) > limit:
            errors[key] = f"Please keep this under {limit} characters."

    include_sample = form["include_sample"] == "1"
    sample = None
    if include_sample:
        sample_id = request.form.get("sample_image_id", type=int)
        sample = db.session.get(ArtImage, sample_id) if sample_id else None
        if sample is None:
            errors["sample_image_id"] = "Please choose which design you'd like as your sample."

    cells = resolve_cells(layout)
    if not cells and not include_sample:
        errors["layout"] = "Your order is empty -- add some tiles or a sample tile."

    if errors:
        return _render_form(layout, form=form, errors=errors)

    q = quote(len(cells), include_sample)
    order = OrderRequest(
        token=secrets.token_urlsafe(16),
        name=form["name"],
        email=form["email"],
        phone=form["phone"] or None,
        address=form["address"],
        notes=form["notes"] or None,
        layout_json=dump_layout(cells),
        tile_count=len(cells),
        include_sample=include_sample,
        sample_image_id=sample.id if sample else None,
        sample_image_title=sample.title if sample else None,
        sample_image_filename=sample.filename if sample else None,
        total_cents=q["total_cents"],
    )
    db.session.add(order)
    db.session.commit()
    send_order_notification(order)
    return redirect(url_for("orders.thanks", token=order.token))


@bp.route("/thanks/<token>")
def thanks(token):
    order = OrderRequest.query.filter_by(token=token).first()
    cells = order.layout if order else []
    return render_template(
        "order_thanks.html", order=order, cells=cells, grid=grid_info(cells) if cells else None
    )
