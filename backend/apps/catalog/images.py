"""
Product photo processing: validate an upload, strip metadata, and store WebP renditions (320/640/1280 px wide,
never upscaled, aspect ratio kept) in Django's configured media storage. Only paths are saved in PostgreSQL.
"""

import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.api.exceptions import DomainError

WIDTHS = (320, 640, 1280)
MAX_BYTES = 8 * 1024 * 1024


def store_upload(image_obj, upload) -> None:
    """Fill `image_obj` (a ProductImage) from an uploaded file. Raises DomainError for unusable files."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if upload.size > MAX_BYTES:
        raise DomainError("Images must be 8 MB or smaller.", code="image_too_large")
    try:
        img = Image.open(upload)
        if img.format not in {"JPEG", "PNG", "WEBP"}:
            raise DomainError("Use a JPG, PNG or WebP image.", code="image_type")
        if img.width * img.height > 50_000_000:
            raise DomainError("That image is too large.", code="image_too_large")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise DomainError("That file isn't a valid image.", code="image_invalid")

    stem = f"products/{image_obj.product_id}/{uuid.uuid4().hex}"
    renditions = {}
    for w in WIDTHS:
        copy = img.copy()
        if copy.width > w:
            copy = copy.resize((w, round(copy.height * w / copy.width)), Image.LANCZOS)
        buf = BytesIO()
        copy.save(buf, "WEBP", quality=82)
        renditions[str(w)] = default_storage.save(f"{stem}-{w}.webp", ContentFile(buf.getvalue()))
        if copy.width < w:
            break  # smaller than this width: no larger renditions
    image_obj.renditions, image_obj.width, image_obj.height = renditions, img.width, img.height


def delete_files(image_obj) -> None:
    for path in (image_obj.renditions or {}).values():
        default_storage.delete(path)


def image_urls(image_obj, request=None) -> dict:
    """{src, srcSet, width, height, alt} for the API; src is the 640 px rendition (or the hosted URL)."""
    if image_obj.renditions:
        urls = {int(w): default_storage.url(p) for w, p in image_obj.renditions.items()}
        if request is not None:
            urls = {w: request.build_absolute_uri(u) for w, u in urls.items()}
        src = urls.get(640) or urls[max(urls)]
        src_set = ", ".join(f"{u} {w}w" for w, u in sorted(urls.items()))
    else:
        src, src_set = image_obj.url, ""
    return {"src": src, "src_set": src_set, "width": image_obj.width, "height": image_obj.height, "alt": image_obj.alt}
