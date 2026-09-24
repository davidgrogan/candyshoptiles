"""Database models.

Every table carries a sync marker in its `info` dict, read by
sync_content.py (the "copy my local data to the droplet" step of
deploy_all.sh):

  CONTENT  -- managed on your laptop through the local admin (images,
              categories, sample sets). sync_content.py *replaces* the
              droplet's copy of these tables with your local copy.
  CUSTOMER -- created by real visitors on the live site (order requests,
              shared designs). sync_content.py never reads, wipes, or
              writes these. Your laptop's copies are just test data.

sync_content.py refuses to run if any table is missing a marker, so a new
table can't silently end up in the wrong bucket -- pick one when you add it.

Customer tables deliberately have NO foreign keys into content tables
(they store image ids/titles inside a JSON snapshot instead). Content
tables get truncated on every sync; a real FK would either block that or,
with CASCADE, take the customer rows down with it.

Adding a NOT NULL column to an existing table? Give it a `server_default=`
too, not just `default=` -- see app/schema_sync.py's docstring.
"""
import json
from datetime import datetime, timezone

import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

CONTENT = {"sync": "content"}
CUSTOMER = {"sync": "customer"}

ORDER_STATUSES = ("new", "contacted", "invoiced", "paid", "shipped", "cancelled")


def utcnow():
    # Naive UTC, so SQLite and Postgres round-trip the same value.
    return datetime.now(timezone.utc).replace(tzinfo=None)


image_categories = db.Table(
    "image_categories",
    db.Column("image_id", db.Integer, db.ForeignKey("art_image.id", ondelete="CASCADE"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("category.id", ondelete="CASCADE"), primary_key=True),
    info=CONTENT,
)


class Category(db.Model):
    __tablename__ = "category"
    __table_args__ = {"info": CONTENT}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")


class ArtImage(db.Model):
    __tablename__ = "art_image"
    __table_args__ = {"info": CONTENT}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    # Base name of the stored files (a uuid hex) -- the actual files are
    # <filename>.jpg and <filename>_thumb.jpg under app/static/uploads/art/.
    # Only the base name is stored, never a URL, so the URL is always built
    # fresh for whichever prefix (local root vs /candyshoptiles) is serving.
    filename = db.Column(db.String(64), nullable=False)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Hidden images stay in admin (and in existing sets/designs) but drop
    # out of the public designer palette.
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=sa.true())
    created_at = db.Column(db.DateTime, default=utcnow)

    categories = db.relationship(
        "Category", secondary=image_categories, backref="images", order_by="Category.sort_order"
    )


class SampleSet(db.Model):
    __tablename__ = "sample_set"
    __table_args__ = {"info": CONTENT}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    # JSON list of {"r", "c", "image_id"} -- see app/layout.py.
    layout_json = db.Column(db.Text, nullable=False, default="[]")
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    is_published = db.Column(db.Boolean, nullable=False, default=True, server_default=sa.true())
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def layout(self):
        return json.loads(self.layout_json or "[]")


class SavedDesign(db.Model):
    """A customer's grid saved for a shareable /d/<slug> link."""

    __tablename__ = "saved_design"
    __table_args__ = {"info": CUSTOMER}

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(16), unique=True, nullable=False, index=True)
    layout_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def layout(self):
        return json.loads(self.layout_json or "[]")


class OrderRequest(db.Model):
    __tablename__ = "order_request"
    __table_args__ = {"info": CUSTOMER}

    id = db.Column(db.Integer, primary_key=True)
    # Unguessable id for the customer's confirmation page.
    token = db.Column(db.String(32), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(20), nullable=False, default="new", server_default="new")

    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    notes = db.Column(db.Text)

    # Snapshot at order time: list of {"r", "c", "image_id", "title",
    # "filename"} -- keeps the order readable even if an image is later
    # renamed or deleted.
    layout_json = db.Column(db.Text, nullable=False, default="[]")
    tile_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    include_sample = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())
    sample_image_id = db.Column(db.Integer)
    sample_image_title = db.Column(db.String(200))
    sample_image_filename = db.Column(db.String(64))
    # Always computed server-side (app/pricing.py), never taken from the form.
    total_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    admin_notes = db.Column(db.Text)

    @property
    def layout(self):
        return json.loads(self.layout_json or "[]")
