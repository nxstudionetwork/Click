"""
Shopping query interpretation: turns a natural-language search into structured filters.

  "black shirt under 1000"      -> colour Black, category Shirts, price <= 1000
  "best headphones under 2000"  -> category Audio, price <= 2000, sort by rating
  "gift for 10 year old boy"    -> gift intent, age 10, categories Toys & Games / Baby & Kids
  "kitchen items for new home"  -> category Kitchen

It is rule-based and only reports what it actually understood (`understood`), so the app never pretends to
understand more than it does. It is the single interpretation boundary for Shopping search and Buddy; a
model-based interpreter can replace `interpret()` later without changing either caller.
"""

import re
from dataclasses import dataclass, field

from apps.catalog.models import Brand, ProductAttributeValue, ShopCategory

STOPWORDS = set("""
a an the me my i we us please find show get give want need buy looking look search some any for to of in on at with and
or is are can you items item things thing stuff products product new good nice best top cheap cheapest affordable budget
under below less than within upto up above over more from between rs inr price priced around about only
""".split())
COLOURS = ["black", "white", "blue", "navy", "red", "green", "olive", "yellow", "pink", "grey", "gray", "brown", "beige",
           "purple", "orange", "silver", "gold", "maroon", "teal", "cream"]
GIFT_WORDS = {"gift", "gifts", "present", "presents", "birthday", "anniversary"}
KID_WORDS = {"kid", "kids", "child", "children", "boy", "girl", "son", "daughter", "toddler", "baby"}
KID_CATEGORY_SLUGS = ["toys-games", "baby-kids"]

_NUM = r"(?:rs\.?|₹|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?"


def _amount(num: str, k: str | None) -> int:
    value = float(num.replace(",", ""))
    return int(value * 1000 if k else value)


@dataclass
class Interpretation:
    text: str
    terms: list[str] = field(default_factory=list)
    category: ShopCategory | None = None
    categories: list[ShopCategory] = field(default_factory=list)  # e.g. gift for a child: several categories
    brand: Brand | None = None
    colour: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    sort: str | None = None
    gift: bool = False
    age: int | None = None
    # The specific word that selected the category (e.g. "shirt" for Men's Clothing). Search narrows to listings
    # named with it when there are any, so "shirt" doesn't return joggers.
    category_word: str | None = None
    understood: list[dict] = field(default_factory=list)  # [{kind, label}] chips shown to the customer

    def as_dict(self) -> dict:
        return {
            "text": self.text, "terms": self.terms,
            "category": self.category.slug if self.category else None,
            "brand": self.brand.slug if self.brand else None, "colour": self.colour,
            "category_word": self.category_word, "min_price": self.min_price, "max_price": self.max_price, "sort": self.sort, "gift": self.gift, "age": self.age,
            "understood": self.understood,
        }


def _category_match(text: str) -> tuple[ShopCategory | None, str | None]:
    """The most specific active category whose name or synonym appears in the text (subcategories win), and the
    synonym that matched (None when the category's own name matched)."""
    best, best_len, word = None, 0, None
    for c in ShopCategory.objects.filter(is_active=True).select_related("parent"):
        words = [c.name.lower()] + [w.strip().lower() for w in c.synonyms.split(",") if w.strip()]
        for w in words:
            for form in {w, w.rstrip("s"), w + "s"}:
                if form and re.search(rf"\b{re.escape(form)}\b", text):
                    score = len(form) + (100 if c.parent_id else 0)
                    if score > best_len:
                        best, best_len, word = c, score, (None if w == c.name.lower() else form)
    return best, word


def interpret(raw: str) -> Interpretation:
    text = " ".join(raw.lower().split())[:200]
    it = Interpretation(text=raw.strip()[:200])
    rest = text

    if m := re.search(rf"\bbetween\s+{_NUM}\s+(?:and|to|-)\s+{_NUM}", rest):
        it.min_price, it.max_price = sorted([_amount(m.group(1), m.group(2)), _amount(m.group(3), m.group(4))])
        rest = rest.replace(m.group(0), " ")
    else:
        if m := re.search(rf"\b(?:under|below|less than|within|upto|up to|max|maximum|cheaper than)\s+{_NUM}", rest):
            it.max_price = _amount(m.group(1), m.group(2))
            rest = rest.replace(m.group(0), " ")
        if m := re.search(rf"\b(?:above|over|more than|min|minimum|starting|from)\s+{_NUM}", rest):
            it.min_price = _amount(m.group(1), m.group(2))
            rest = rest.replace(m.group(0), " ")
    if it.min_price is not None and it.max_price is not None:
        it.understood.append({"kind": "price", "label": f"₹{it.min_price:,}–₹{it.max_price:,}"})
    elif it.max_price is not None:
        it.understood.append({"kind": "price", "label": f"Under ₹{it.max_price:,}"})
    elif it.min_price is not None:
        it.understood.append({"kind": "price", "label": f"Above ₹{it.min_price:,}"})

    if m := re.search(r"\b(\d{1,2})\s*(?:-|\s)?\s*(?:year|yr)s?\s*(?:-|\s)?\s*old\b", rest):
        it.age = int(m.group(1))
        rest = rest.replace(m.group(0), " ")

    words = set(re.findall(r"[a-z0-9&']+", rest))
    if words & GIFT_WORDS:
        it.gift = True
        it.sort = it.sort or "rating"
        it.understood.append({"kind": "intent", "label": "Gift ideas"})
    if words & {"best", "top"}:
        it.sort = "rating"
        it.understood.append({"kind": "sort", "label": "Top rated first"})
    elif words & {"cheap", "cheapest", "affordable", "budget"}:
        it.sort = "price_asc"
        it.understood.append({"kind": "sort", "label": "Lowest price first"})

    for brand in Brand.objects.filter(is_active=True).only("id", "name", "slug"):
        if re.search(rf"\b{re.escape(brand.name.lower())}\b", rest):
            it.brand = brand
            rest = re.sub(rf"\b{re.escape(brand.name.lower())}\b", " ", rest)
            it.understood.append({"kind": "brand", "label": brand.name})
            break

    for colour in COLOURS:
        if re.search(rf"\b{colour}\b", rest) and _colour_exists(colour):
            it.colour = "Grey" if colour == "gray" else colour.title()
            rest = re.sub(rf"\b{colour}\b", " ", rest)
            it.understood.append({"kind": "colour", "label": it.colour})
            break

    audience = (it.age is not None and it.age < 14) or bool(words & {"kid", "kids", "toddler", "baby"}) or (it.gift and bool(words & KID_WORDS))
    if audience:  # "boy"/"girl" describe who it's for, not a clothing category
        for w in KID_WORDS:
            rest = re.sub(rf"\b{w}s?\b", " ", rest)
    cat, word = _category_match(rest)
    if cat:
        it.category, it.category_word = cat, word
        for w in [cat.name.lower()] + [s.strip().lower() for s in cat.synonyms.split(",") if s.strip()]:
            rest = re.sub(rf"\b{re.escape(w)}s?\b", " ", rest)
        it.understood.append({"kind": "category", "label": cat.name})
    elif audience:
        it.categories = list(ShopCategory.objects.filter(slug__in=KID_CATEGORY_SLUGS, is_active=True))
        if it.categories:
            it.understood.append({"kind": "audience", "label": "For kids"})
    if it.age is not None:
        it.understood.append({"kind": "age", "label": f"Age {it.age}"})
    for w in KID_WORDS | GIFT_WORDS | {"year", "old", "boy", "girl"}:
        rest = re.sub(rf"\b{w}\b", " ", rest)

    it.terms = [w for w in re.findall(r"[a-z0-9&']+", rest) if w not in STOPWORDS and len(w) > 1 and not w.isdigit()][:5]
    return it


def _colour_exists(colour: str) -> bool:
    """Only treat a word as a colour filter when listings actually have that colour."""
    from apps.catalog.models import ProductVariant

    name = "Grey" if colour == "gray" else colour.title()
    return (ProductAttributeValue.objects.filter(definition__code="color", value__iexact=name).exists()
            or ProductVariant.objects.filter(is_active=True, options__Color=name).exists())
