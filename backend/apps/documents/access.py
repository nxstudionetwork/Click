"""
Who may see or change a document is decided by the module that owns the record it's attached to.

    from apps.documents.access import register

    @register("people.employee")
    def employee_documents(ctx, resource_id, action, document=None) -> bool: ...

`action` is one of: view, upload, verify, archive. An unregistered resource type is closed to everyone.
"""

_CHECKERS: dict = {}


def register(resource_type: str):
    def deco(fn):
        _CHECKERS[resource_type] = fn
        return fn
    return deco


def allowed(ctx, resource_type: str, resource_id: str, action: str, document=None) -> bool:
    fn = _CHECKERS.get(resource_type)
    return bool(fn and fn(ctx, resource_id, action, document))


def registered_types() -> list[str]:
    return sorted(_CHECKERS)
