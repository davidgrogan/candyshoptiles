import secrets

from flask import Blueprint, jsonify, render_template, request, url_for

from app.auth import is_admin
from app.catalog import designer_config, grid_info, image_ids, resolve_cells
from app.layout import LayoutError, dump_layout, parse_layout, parse_spacing
from app.models import SampleSet, SavedDesign, db
from app.pricing import quote

bp = Blueprint("main", __name__)


@bp.route("/")
def designer():
    initial, spacing, notice = None, None, None
    set_id = request.args.get("set", type=int)
    if set_id:
        sample_set = db.session.get(SampleSet, set_id)
        if sample_set and (sample_set.is_published or is_admin()):
            initial, spacing = sample_set.layout, sample_set.spacing_in
            notice = f"Starting from the “{sample_set.name}” set -- swap, add or remove tiles to make it yours."
    return render_template("designer.html", config=designer_config(initial, initial_spacing=spacing), notice=notice)


@bp.route("/d/<slug>")
def shared_design(slug):
    design = SavedDesign.query.filter_by(slug=slug).first_or_404()
    return render_template(
        "designer.html",
        config=designer_config(design.layout, initial_spacing=design.spacing_in),
        notice="Someone shared this design with you. Change anything you like, or order it as is.",
    )


@bp.route("/api/designs", methods=["POST"])
def save_design():
    payload = request.get_json(silent=True) or {}
    try:
        layout = parse_layout(payload.get("layout", []), image_ids())
    except LayoutError as exc:
        return jsonify(error=str(exc)), 400
    if not layout:
        return jsonify(error="Add at least one tile before sharing."), 400
    design = SavedDesign(slug=secrets.token_urlsafe(8)[:10], layout_json=dump_layout(layout),
                         spacing_in=parse_spacing(payload.get("spacing")))
    db.session.add(design)
    db.session.commit()
    return jsonify(url=url_for("main.shared_design", slug=design.slug, _external=True))


@bp.route("/sets")
def sample_sets():
    sets = []
    for s in SampleSet.query.filter_by(is_published=True).order_by(SampleSet.sort_order, SampleSet.id):
        cells = resolve_cells(s.layout)
        if cells:
            sets.append({"set": s, "cells": cells, "grid": grid_info(cells, s.spacing_in), "quote": quote(len(cells))})
    return render_template("sets.html", sets=sets)


@bp.route("/healthz")
def healthz():
    return "ok"


@bp.app_errorhandler(404)
def not_found(_):
    return render_template("error.html", title="Page not found",
                           message="That page doesn't exist -- it may have been moved or deleted."), 404


@bp.app_errorhandler(400)
def bad_request(exc):
    return render_template("error.html", title="Something went wrong",
                           message=getattr(exc, "description", None) or "That request couldn't be processed."), 400


@bp.app_errorhandler(413)
def too_large(_):
    return render_template("error.html", title="Upload too large",
                           message="That upload was too big. Try fewer or smaller images at once."), 413
