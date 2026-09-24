import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.images import save_pil_image  # noqa: E402
from app.models import ArtImage, db  # noqa: E402


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.sqlite3'}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "CSRF_ENABLED": False,
        "SERVER_NAME": "localhost",
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def images(app):
    """Three stored placeholder images; returns their ids."""
    ids = []
    with app.app_context():
        for i, color in enumerate(["red", "green", "blue"]):
            base, w, h = save_pil_image(Image.new("RGB", (80, 100), color))
            img = ArtImage(title=f"Tile {i}", filename=base, width=w, height=h, sort_order=i)
            db.session.add(img)
            db.session.flush()
            ids.append(img.id)
        db.session.commit()
    return ids


@pytest.fixture
def admin_client(client):
    with client.session_transaction() as s:
        s["is_admin"] = True
    return client
