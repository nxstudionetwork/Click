"""Profile photo processing shared by every Click app (customer profile, Business OS account)."""

import uuid
from io import BytesIO

from django.core.files.base import ContentFile

from apps.core.api.exceptions import DomainError

MAX_BYTES = 5 * 1024 * 1024


def encode_avatar(upload) -> ContentFile:
    """Validate an uploaded image and return a square 512px WebP (re-encoding drops EXIF such as location)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if upload is None:
        raise DomainError("Choose an image to upload.", code="image_required")
    if upload.size > MAX_BYTES:
        raise DomainError("Images must be 5 MB or smaller.", code="image_too_large")
    try:
        img = Image.open(upload)
        if img.format not in {"JPEG", "PNG", "WEBP"}:
            raise DomainError("Use a JPG, PNG or WebP image.", code="image_type")
        if img.width * img.height > 40_000_000:
            raise DomainError("That image is too large.", code="image_too_large")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise DomainError("That file isn’t a valid image.", code="image_invalid")
    img = ImageOps.fit(img, (512, 512), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, "WEBP", quality=82)
    return ContentFile(buf.getvalue(), name=f"{uuid.uuid4().hex}.webp")
