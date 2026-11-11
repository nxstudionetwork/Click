"""
Photos for Services: customers' problem photos, professionals' profile photos and portfolio images. Each upload is
checked (type, size, pixels), EXIF metadata (including GPS) is stripped and WebP renditions are stored in Django's media
storage; only storage paths are kept in PostgreSQL. Files live under random UUID paths.
"""

import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.api.exceptions import DomainError

MAX_BYTES = 8 * 1024 * 1024
WIDTHS = (320, 960)


def _open(upload):
    from PIL import Image, ImageOps, UnidentifiedImageError

    if upload.size > MAX_BYTES:
        raise DomainError("Photos must be 8 MB or smaller.", code="image_too_large")
    try:
        img = Image.open(upload)
        if img.format not in {"JPEG", "PNG", "WEBP"}:
            raise DomainError("Use a JPG, PNG or WebP photo.", code="image_type")
        if img.width * img.height > 50_000_000:
            raise DomainError("That photo is too large.", code="image_too_large")
        return ImageOps.exif_transpose(img).convert("RGB")  # re-encoding drops all metadata
    except (UnidentifiedImageError, OSError):
        raise DomainError("That file isn't a valid photo.", code="image_invalid")


def store(obj, upload, folder: str) -> None:
    """Fill obj.renditions / width / height from an upload."""
    from PIL import Image

    img = _open(upload)
    stem = f"{folder}/{uuid.uuid4().hex}"
    out = {}
    for w in WIDTHS:
        copy = img.copy()
        if copy.width > w:
            copy = copy.resize((w, round(copy.height * w / copy.width)), Image.LANCZOS)
        buf = BytesIO()
        copy.save(buf, "WEBP", quality=82)
        out[str(w)] = default_storage.save(f"{stem}-{w}.webp", ContentFile(buf.getvalue()))
        if copy.width < w:
            break
    obj.renditions, obj.width, obj.height = out, img.width, img.height


def profile_photo(upload) -> ContentFile:
    """A square-cropped 480 px WebP for ProviderProfile.photo."""
    from PIL import Image, ImageOps

    img = ImageOps.fit(_open(upload), (480, 480), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, "WEBP", quality=84)
    return ContentFile(buf.getvalue(), name=f"{uuid.uuid4().hex}.webp")


def urls(obj, request=None) -> dict:
    r = {int(w): default_storage.url(p) for w, p in (obj.renditions or {}).items()}
    if request is not None:
        r = {w: request.build_absolute_uri(u) for w, u in r.items()}
    if not r:
        return {"src": "", "thumb": ""}
    return {"src": r.get(960) or r[max(r)], "thumb": r.get(320) or r[min(r)], "width": obj.width, "height": obj.height}


def delete(obj) -> None:
    for p in (obj.renditions or {}).values():
        default_storage.delete(p)
