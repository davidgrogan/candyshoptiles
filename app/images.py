"""Storing art images.

Every upload is opened and re-encoded with Pillow, which checks that it's
really an image (not just a file named .jpg), applies the phone camera's
EXIF rotation, strips metadata (including GPS), and caps the size. Two
JPEGs are written per image, named by a random uuid:

    app/static/uploads/art/<uuid>.jpg        up to 2000px, the wall view + zoom
    app/static/uploads/art/<uuid>_thumb.jpg  up to 480px, the palette + grid

That directory is gitignored; deploy_all.sh rsyncs it to the droplet.
"""
import os
import uuid

from flask import current_app, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

FULL_MAX = 2000
THUMB_MAX = 480
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO", "GIF"}

# Refuse absurd dimensions outright (Pillow raises DecompressionBombError).
Image.MAX_IMAGE_PIXELS = 60_000_000


class ImageUploadError(ValueError):
    pass


def upload_dir():
    path = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(path, exist_ok=True)
    return path


def image_url(filename, size="thumb"):
    suffix = "_thumb" if size == "thumb" else ""
    return url_for("static", filename=f"uploads/art/{filename}{suffix}.jpg")


def _to_rgb(img):
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    return img.convert("RGB")


def save_pil_image(img):
    """Write full + thumb JPEGs for an already-open PIL image; returns
    (basename, width, height) of the full-size version."""
    img = _to_rgb(img)
    full = img.copy()
    full.thumbnail((FULL_MAX, FULL_MAX), Image.LANCZOS)
    thumb = img.copy()
    thumb.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
    base = uuid.uuid4().hex
    directory = upload_dir()
    full.save(os.path.join(directory, f"{base}.jpg"), "JPEG", quality=88, optimize=True, progressive=True)
    thumb.save(os.path.join(directory, f"{base}_thumb.jpg"), "JPEG", quality=82, optimize=True)
    return base, full.width, full.height


def save_upload(file_storage):
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageUploadError(f"“{file_storage.filename}” isn't a readable image.") from exc
    if img.format not in ALLOWED_FORMATS:
        raise ImageUploadError(f"“{file_storage.filename}” is a {img.format} file -- use JPEG, PNG or WebP.")
    return save_pil_image(img)


def delete_files(basename):
    directory = upload_dir()
    for name in (f"{basename}.jpg", f"{basename}_thumb.jpg"):
        try:
            os.remove(os.path.join(directory, name))
        except FileNotFoundError:
            pass
