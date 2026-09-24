"""Seed a fresh local database with placeholder tile art, categories and a
few sample sets, so the designer has something in it before real art
exists.

    python seed.py

Only runs against an empty image library -- it never adds duplicates or
touches anything you've added through the admin. Run it locally; the
droplet gets this content through deploy_all.sh's content sync, same as
anything else you add locally.
"""
from app import create_app
from app.images import save_pil_image
from app.layout import dump_layout
from app.models import ArtImage, Category, SampleSet, db
from app.placeholders import PLACEHOLDER_ART, make_art

CATEGORY_ORDER = ["Stripes", "Dots & Circles", "Geometric", "Florals"]

# (name, description, rows of titles; None = gap)
SAMPLE_SETS = [
    ("Candy Stripe Trio", "Three stripes in a row -- made for above a sofa or bed.",
     [["Taffy Stripe", "Ribbon Candy", "Blueberry Stripe"]]),
    ("Sweet Quad", "Four favorites in a tidy square.",
     [["Gumdrop Dots", "Sugar Bloom"], ["Lemon Sun", "Jawbreaker"]]),
    ("Tall Stack", "A column of three for a narrow wall or hallway.",
     [["Rainbow Drop"], ["Scallop Shell"], ["Lemon Drops"]]),
    ("The Whole Candy Shop", "A big nine-tile statement wall.",
     [["Taffy Stripe", "Cobalt Sun", "Gumdrop Dots"],
      ["Midnight Bloom", "Jawbreaker", "Checkerboard Fudge"],
      ["Lemon Drops", "Candy Corn Shards", "Sugar Bloom"]]),
]


def main():
    app = create_app()
    with app.app_context():
        if ArtImage.query.count():
            print("Images already exist -- not seeding (seed.py only fills an empty library).")
            return

        cats = {}
        for i, name in enumerate(CATEGORY_ORDER):
            cats[name] = Category.query.filter_by(name=name).first() or Category(name=name, sort_order=i)
            db.session.add(cats[name])

        by_title = {}
        for i, (title, pattern, fg, bg, cat_names) in enumerate(PLACEHOLDER_ART):
            base, w, h = save_pil_image(make_art(pattern, fg, bg, seed=i))
            img = ArtImage(title=title, filename=base, width=w, height=h, sort_order=i,
                           categories=[cats[c] for c in cat_names])
            db.session.add(img)
            by_title[title] = img
        db.session.flush()

        for i, (name, desc, rows) in enumerate(SAMPLE_SETS):
            layout = [
                {"r": r, "c": c, "image_id": by_title[title].id}
                for r, row in enumerate(rows) for c, title in enumerate(row) if title
            ]
            db.session.add(SampleSet(name=name, description=desc, layout_json=dump_layout(layout), sort_order=i))

        db.session.commit()
        print(f"Seeded {len(by_title)} placeholder images, {len(cats)} categories, {len(SAMPLE_SETS)} sample sets.")


if __name__ == "__main__":
    main()
