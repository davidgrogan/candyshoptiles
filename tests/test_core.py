import io
import json

import pytest
from PIL import Image
from sqlalchemy import create_engine, text

from app.layout import LayoutError, dimensions, parse_layout
from app.models import OrderRequest, SavedDesign, db
from app.pricing import quote


# --- pricing -----------------------------------------------------------------

@pytest.mark.parametrize("n, sample, total", [
    (0, False, 0),
    (0, True, 2900),
    (1, False, 4900),
    (2, False, 7800),
    (4, False, 15600),
    (3, True, 3 * 3900 + 2900),
])
def test_quote(n, sample, total):
    assert quote(n, sample)["total_cents"] == total


# --- layout ------------------------------------------------------------------

def test_layout_normalizes_and_filters():
    raw = [{"r": 5, "c": 3, "image_id": 1}, {"r": 6, "c": 3, "image_id": 99}, {"r": 5, "c": 4, "image_id": 2}]
    assert parse_layout(json.dumps(raw), {1, 2}) == [
        {"r": 0, "c": 0, "image_id": 1},
        {"r": 0, "c": 1, "image_id": 2},
    ]


def test_layout_accepts_gaps_and_any_direction():
    layout = parse_layout([{"r": 0, "c": 0, "image_id": 1}, {"r": 2, "c": 0, "image_id": 1}], {1})
    assert dimensions(layout) == (3, 1)


def test_layout_rejects_oversize_and_garbage():
    with pytest.raises(LayoutError):
        parse_layout([{"r": 0, "c": 0, "image_id": 1}, {"r": 0, "c": 12, "image_id": 1}], {1})
    with pytest.raises(LayoutError):
        parse_layout("not json", {1})
    with pytest.raises(LayoutError):
        parse_layout([{"r": "x", "c": 0, "image_id": 1}], {1})


# --- pages -------------------------------------------------------------------

def test_public_pages_render(client, images):
    for url in ["/", "/sets", "/order/start", "/healthz"]:
        assert client.get(url).status_code == 200, url


def test_admin_requires_login(client):
    resp = client.get("/admin/images")
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]


def test_admin_pages_render(admin_client, images):
    for url in ["/admin/", "/admin/images", "/admin/images/new", f"/admin/images/{images[0]}/edit",
                "/admin/categories", "/admin/sets", "/admin/sets/new", "/admin/orders"]:
        assert admin_client.get(url).status_code == 200, url


# --- orders ------------------------------------------------------------------

def _order(client, layout, **fields):
    data = {"layout": json.dumps(layout), "name": "Pat", "email": "pat@example.com", "address": "1 Main St"}
    data.update(fields)
    return client.post("/order", data=data)


def test_order_total_is_computed_server_side(app, client, images):
    layout = [{"r": 0, "c": i, "image_id": images[i]} for i in range(3)]
    resp = _order(client, layout, total_cents="1")  # a bogus total field is ignored
    assert resp.status_code == 302
    with app.app_context():
        order = OrderRequest.query.one()
        assert order.tile_count == 3
        assert order.total_cents == 3 * 3900
        assert [t["title"] for t in order.layout] == ["Tile 0", "Tile 1", "Tile 2"]
    assert client.get(resp.headers["Location"]).status_code == 200


def test_sample_only_order(app, client, images):
    resp = _order(client, [], include_sample="1", sample_image_id=str(images[1]))
    assert resp.status_code == 302
    with app.app_context():
        order = OrderRequest.query.one()
        assert (order.tile_count, order.total_cents, order.sample_image_title) == (0, 2900, "Tile 1")


def test_empty_order_rejected(app, client, images):
    assert _order(client, []).status_code == 400
    with app.app_context():
        assert OrderRequest.query.count() == 0


def test_honeypot_saves_nothing(app, client, images):
    resp = _order(client, [{"r": 0, "c": 0, "image_id": images[0]}], website="http://spam")
    assert resp.status_code == 302
    with app.app_context():
        assert OrderRequest.query.count() == 0


# --- share links ---------------------------------------------------------------

def test_share_link_round_trip(app, client, images):
    resp = client.post("/api/designs", json={"layout": [{"r": 0, "c": 0, "image_id": images[2]}]})
    assert resp.status_code == 200
    url = resp.get_json()["url"]
    slug = url.rsplit("/", 1)[-1]
    with app.app_context():
        assert SavedDesign.query.filter_by(slug=slug).one().layout == [{"r": 0, "c": 0, "image_id": images[2]}]
    assert client.get(f"/d/{slug}").status_code == 200


# --- CSRF --------------------------------------------------------------------

def test_csrf_blocks_post_without_token(app, client, images):
    app.config["CSRF_ENABLED"] = True
    assert _order(client, [{"r": 0, "c": 0, "image_id": images[0]}]).status_code == 400


# --- admin writes --------------------------------------------------------------

def test_admin_upload_rejects_non_images(app, admin_client):
    ok = io.BytesIO()
    Image.new("RGB", (40, 50), "pink").save(ok, "PNG")
    ok.seek(0)
    resp = admin_client.post("/admin/images/new", data={
        "files": [(ok, "my-new_tile.png"), (io.BytesIO(b"not an image"), "evil.jpg")],
    }, content_type="multipart/form-data")
    assert resp.status_code == 302
    with app.app_context():
        from app.models import ArtImage
        assert [i.title for i in ArtImage.query.all()] == ["my new tile"]


def test_admin_set_create(app, admin_client, images):
    layout = [{"r": 0, "c": 0, "image_id": images[0]}, {"r": 1, "c": 0, "image_id": images[1]}]
    resp = admin_client.post("/admin/sets/new", data={"name": "Duo", "layout": json.dumps(layout), "is_published": "1"})
    assert resp.status_code == 302
    assert b"Duo" in admin_client.get("/sets").data


# --- schema + content sync -------------------------------------------------------

def test_every_table_has_a_sync_marker():
    from sync_content import classify_tables

    content, customer = classify_tables()
    assert "order_request" in customer and "saved_design" in customer
    assert "art_image" in content and content.index("art_image") < content.index("image_categories")


def test_sqlite_startup_adds_missing_columns(tmp_path):
    from app import create_app

    path = tmp_path / "old.sqlite3"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:  # an "old" category table missing sort_order
        conn.execute(text("CREATE TABLE category (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE)"))
        conn.execute(text("INSERT INTO category (name) VALUES ('Old')"))
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}", "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        rows = db.session.execute(text("SELECT name, sort_order FROM category")).all()
    assert rows == [("Old", 0)]


def test_content_sync_leaves_customer_tables_alone(app, images, tmp_path):
    from sqlalchemy import MetaData

    from sync_content import classify_tables, copy_content

    src_engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"])
    dst_path = tmp_path / "droplet.sqlite3"
    from app import create_app

    droplet = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{dst_path}", "UPLOAD_FOLDER": str(tmp_path)})
    with droplet.app_context():
        db.session.add(OrderRequest(token="t", name="Real customer", email="c@example.com", layout_json="[]"))
        db.session.execute(text("INSERT INTO art_image (title, filename, sort_order, is_active) VALUES ('stale', 'x', 0, 1)"))
        db.session.commit()
    dst_engine = create_engine(f"sqlite:///{dst_path}")

    content, _ = classify_tables()
    src_meta, dst_meta = MetaData(), MetaData()
    src_meta.reflect(bind=src_engine, only=content)
    dst_meta.reflect(bind=dst_engine, only=content)
    copy_content(src_engine, dst_engine, content, src_meta, dst_meta, log=lambda *_: None)

    with dst_engine.connect() as conn:
        titles = [r[0] for r in conn.execute(text("SELECT title FROM art_image ORDER BY id"))]
        orders = [r[0] for r in conn.execute(text("SELECT name FROM order_request"))]
    assert titles == ["Tile 0", "Tile 1", "Tile 2"]
    assert orders == ["Real customer"]
