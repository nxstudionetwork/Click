import logging

logger = logging.getLogger(__name__)


def record(customer, verb: str, metadata: dict | None = None, *, obj=None) -> None:
    """Best-effort event recording; never breaks the business action that triggered it."""
    from .models import CustomerActivity

    try:
        CustomerActivity.objects.create(customer=customer, verb=verb, metadata=metadata or {},
                                        object_type=obj._meta.label_lower if obj is not None else "",
                                        object_id=getattr(obj, "pk", None))
    except Exception:  # pragma: no cover
        logger.exception("could not record activity %s", verb)
