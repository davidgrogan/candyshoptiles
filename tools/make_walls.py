"""Regenerate the placeholder wall backgrounds in app/static/walls/.

    python tools/make_walls.py

These are committed to git (they're part of the site, not uploaded
content). Swap in real photos any time by replacing the .jpg files.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.placeholders import make_wall_entry, make_wall_painted, make_wall_sofa  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "walls")

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in [("painted", make_wall_painted), ("sofa", make_wall_sofa), ("entry", make_wall_entry)]:
        path = os.path.join(OUT, f"{name}.jpg")
        fn().save(path, "JPEG", quality=85, optimize=True, progressive=True)
        print("wrote", path)
