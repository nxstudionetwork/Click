"""
Visual (image) search boundary. A provider turns a photo into search words; Shopping search does the rest, so
results are always real listings. No provider is configured today (CLICK_VISION_PROVIDER is empty), so the app
hides the camera button (GET /customer/assistant/capabilities -> visualSearch: false) and this endpoint says so.

A provider is a class with:  def keywords(self, image_file) -> list[str]
Configure it with CLICK_VISION_PROVIDER="package.module.ClassName". It must not be a Google Cloud / Gemini service.
"""

from django.conf import settings
from django.utils.module_loading import import_string

from apps.core.api.exceptions import DomainError


def provider():
    path = settings.CLICK_VISION_PROVIDER
    if not path:
        return None
    return import_string(path)()


def keywords_for(image_file) -> list[str]:
    p = provider()
    if p is None:
        raise DomainError("Image search isn't available yet. Search by text or voice instead.", code="visual_search_unavailable",
                          status_code=503)
    words = [w.strip().lower() for w in p.keywords(image_file) if w and w.strip()]
    if not words:
        raise DomainError("We couldn't recognise a product in that photo. Try another photo or search by text.", code="visual_search_no_match")
    return words[:5]
