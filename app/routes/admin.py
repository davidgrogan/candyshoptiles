"""Admin: art images, categories, sample sets, and incoming order requests.

Content (images/categories/sets) is meant to be managed on your laptop and
pushed up by deploy_all.sh -- its data-sync step replaces the droplet's
content tables with your local copy. Orders are the opposite: they only
ever come in on the live site, and the sync never touches them. Admin
pages show a reminder banner when they're running against Postgres.
"""
import os
from urllib.parse import unquote_plus

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth import require_admin
from app.catalog import designer_config, grid_info, image_ids, resolve_cells
from app.images import ImageUploadError, delete_files, save_upload
from app.layout import LayoutError, dump_layout, parse_layout, parse_spacing
from app.models import ORDER_STATUSES, ArtImage, Category, OrderRequest, SampleSet, db

bp = Blueprint("admin", __name__, url_prefix="/admin")
bp.before_request(require_admin)


@bp.context_processor
def inject_admin_flags():
    return {"is_live_db": db.engine.dialect.name != "sqlite", "order_statuses": ORDER_STATUSES}


def _int(name, default=0):
    try:
        return int(request.form.get(name) or default)
    except ValueError:
        return default


def _selected_categories():
    ids = [int(x) for x in request.form.getlist("categories") if x.isdigit()]
    return Category.query.filter(Category.id.in_(ids)).all() if ids else []


@bp.route("/")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        image_count=ArtImage.query.count(),
        set_count=SampleSet.query.count(),
        new_orders=OrderRequest.query.filter_by(status="new").count(),
        recent_orders=OrderRequest.query.order_by(OrderRequest.created_at.desc()).limit(5).all(),
    )


# --- Images ------------------------------------------------------------------

@bp.route("/images")
def images():
    all_images = ArtImage.query.order_by(ArtImage.sort_order, ArtImage.id).all()
    return render_template("admin/images.html", images=all_images)


@bp.route("/images/new", methods=["GET", "POST"])
def image_new():
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    if request.method == "POST":
        files = [f for f in request.files.getlist("files") if f and f.filename]
        if not files:
            flash("Choose at least one image to upload.", "error")
            return render_template("admin/image_new.html", categories=categories), 400
        chosen = _selected_categories()
        next_order = (db.session.query(db.func.max(ArtImage.sort_order)).scalar() or 0) + 1
        added, problems = 0, []
        for f in files:
            try:
                base, w, h = save_upload(f)
            except ImageUploadError as exc:
                problems.append(str(exc))
                continue
            # "Kala%27s+Arrival.jpg" (web-encoded) / "my_new-tile.png" -> readable titles
            stem = unquote_plus(os.path.splitext(os.path.basename(f.filename))[0])
            title = " ".join(stem.replace("_", " ").replace("-", " ").split())
            db.session.add(ArtImage(title=(title or "Untitled")[:200], filename=base, width=w, height=h,
                                    sort_order=next_order, categories=list(chosen)))
            next_order += 1
            added += 1
        db.session.commit()
        for p in problems:
            flash(p, "error")
        if added:
            flash(f"Added {added} image{'s' if added != 1 else ''}. Titles came from the file names -- edit them below.",
                  "success")
        return redirect(url_for("admin.images"))
    return render_template("admin/image_new.html", categories=categories)


@bp.route("/images/<int:image_id>/edit", methods=["GET", "POST"])
def image_edit(image_id):
    image = db.session.get(ArtImage, image_id) or abort(404)
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Title can't be blank.", "error")
            return render_template("admin/image_edit.html", image=image, categories=categories), 400
        replacement = request.files.get("file")
        if replacement and replacement.filename:
            try:
                base, w, h = save_upload(replacement)
            except ImageUploadError as exc:
                flash(str(exc), "error")
                return render_template("admin/image_edit.html", image=image, categories=categories), 400
            old = image.filename
            image.filename, image.width, image.height = base, w, h
        else:
            old = None
        image.title = title[:200]
        image.description = (request.form.get("description") or "").strip() or None
        image.sort_order = _int("sort_order", image.sort_order)
        image.is_active = request.form.get("is_active") == "1"
        image.categories = _selected_categories()
        db.session.commit()
        if old:
            delete_files(old)
        flash(f"Saved “{image.title}”.", "success")
        return redirect(url_for("admin.images"))
    return render_template("admin/image_edit.html", image=image, categories=categories,
                           used_in=_sets_using(image.id))


@bp.route("/images/<int:image_id>/delete", methods=["POST"])
def image_delete(image_id):
    image = db.session.get(ArtImage, image_id) or abort(404)
    filename, title = image.filename, image.title
    db.session.delete(image)
    db.session.commit()
    delete_files(filename)
    flash(f"Deleted “{title}”. Any sample sets using it just lose that tile.", "success")
    return redirect(url_for("admin.images"))


def _sets_using(image_id):
    return [s for s in SampleSet.query.all() if any(t["image_id"] == image_id for t in s.layout)]


# --- Categories --------------------------------------------------------------

@bp.route("/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:80]
        if not name:
            flash("Category name can't be blank.", "error")
        elif Category.query.filter(db.func.lower(Category.name) == name.lower()).first():
            flash(f"There's already a category called “{name}”.", "error")
        else:
            db.session.add(Category(name=name, sort_order=_int("sort_order")))
            db.session.commit()
            flash(f"Added “{name}”.", "success")
        return redirect(url_for("admin.categories"))
    cats = Category.query.order_by(Category.sort_order, Category.name).all()
    return render_template("admin/categories.html", categories=cats)


@bp.route("/categories/<int:category_id>", methods=["POST"])
def category_update(category_id):
    cat = db.session.get(Category, category_id) or abort(404)
    name = (request.form.get("name") or "").strip()[:80]
    clash = Category.query.filter(db.func.lower(Category.name) == name.lower(), Category.id != cat.id).first()
    if not name or clash:
        flash("That name is blank or already used.", "error")
    else:
        cat.name = name
        cat.sort_order = _int("sort_order", cat.sort_order)
        db.session.commit()
        flash(f"Saved “{name}”.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
def category_delete(category_id):
    cat = db.session.get(Category, category_id) or abort(404)
    db.session.delete(cat)
    db.session.commit()
    flash(f"Deleted category “{cat.name}” (its images are untouched).", "success")
    return redirect(url_for("admin.categories"))


# --- Sample sets -------------------------------------------------------------

@bp.route("/sets")
def sets():
    rows = []
    for s in SampleSet.query.order_by(SampleSet.sort_order, SampleSet.id):
        cells = resolve_cells(s.layout)
        rows.append({"set": s, "cells": cells, "grid": grid_info(cells, s.spacing_in)})
    return render_template("admin/sets.html", rows=rows)


def _set_form(sample_set, keep_submitted=False):
    layout, spacing = sample_set.layout, sample_set.spacing_in
    if keep_submitted:
        spacing = parse_spacing(request.form.get("spacing"), default=spacing)
        # Re-show what was on the board when the save failed validation,
        # not the last saved version.
        try:
            layout = parse_layout(request.form.get("layout", "[]"), image_ids())
        except LayoutError:
            pass
    return render_template(
        "admin/set_form.html",
        sample_set=sample_set,
        form=request.form if keep_submitted else None,
        config=designer_config(layout, mode="admin", include_hidden=True, initial_spacing=spacing),
    )


def _save_set(sample_set):
    name = (request.form.get("name") or "").strip()[:200]
    try:
        layout = parse_layout(request.form.get("layout", "[]"), image_ids())
    except LayoutError as exc:
        flash(str(exc), "error")
        return None
    if not name:
        flash("Give the set a name.", "error")
        return None
    if not layout:
        flash("Add at least one tile to the set.", "error")
        return None
    sample_set.name = name
    sample_set.description = (request.form.get("description") or "").strip() or None
    sample_set.sort_order = _int("sort_order", sample_set.sort_order or 0)
    sample_set.is_published = request.form.get("is_published") == "1"
    sample_set.layout_json = dump_layout(layout)
    sample_set.spacing_in = parse_spacing(request.form.get("spacing"))
    return sample_set


@bp.route("/sets/new", methods=["GET", "POST"])
def set_new():
    sample_set = SampleSet(is_published=True, layout_json="[]", sort_order=0)
    if request.method == "POST":
        if _save_set(sample_set):
            db.session.add(sample_set)
            db.session.commit()
            flash(f"Created “{sample_set.name}”.", "success")
            return redirect(url_for("admin.sets"))
        return _set_form(sample_set, keep_submitted=True), 400
    return _set_form(sample_set)


@bp.route("/sets/<int:set_id>/edit", methods=["GET", "POST"])
def set_edit(set_id):
    sample_set = db.session.get(SampleSet, set_id) or abort(404)
    if request.method == "POST":
        if _save_set(sample_set):
            db.session.commit()
            flash(f"Saved “{sample_set.name}”.", "success")
            return redirect(url_for("admin.sets"))
        return _set_form(sample_set, keep_submitted=True), 400
    return _set_form(sample_set)


@bp.route("/sets/<int:set_id>/delete", methods=["POST"])
def set_delete(set_id):
    sample_set = db.session.get(SampleSet, set_id) or abort(404)
    db.session.delete(sample_set)
    db.session.commit()
    flash(f"Deleted “{sample_set.name}”.", "success")
    return redirect(url_for("admin.sets"))


# --- Orders ------------------------------------------------------------------

@bp.route("/orders")
def orders():
    status = request.args.get("status") or ""
    query = OrderRequest.query
    if status in ORDER_STATUSES:
        query = query.filter_by(status=status)
    return render_template("admin/orders.html", orders=query.order_by(OrderRequest.created_at.desc()).all(),
                           status=status)


@bp.route("/orders/<int:order_id>", methods=["GET", "POST"])
def order_detail(order_id):
    order = db.session.get(OrderRequest, order_id) or abort(404)
    if request.method == "POST":
        status = request.form.get("status")
        if status in ORDER_STATUSES:
            order.status = status
        order.admin_notes = (request.form.get("admin_notes") or "").strip() or None
        db.session.commit()
        flash("Order updated.", "success")
        return redirect(url_for("admin.order_detail", order_id=order.id))
    cells = order.layout
    return render_template("admin/order_detail.html", order=order, cells=cells,
                           grid=grid_info(cells, order.spacing_in) if cells else None)
