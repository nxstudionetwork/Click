"""
Module hooks for the approval engine. A module registers what happens when one of its requests is finally decided:

    from apps.workflows.hooks import on_decision

    @on_decision("people.leave")
    def apply_leave(req, outcome):          # outcome: approved | rejected | cancelled | changes_requested
        ...

Hooks run inside the engine's transaction, so the module change and the approval outcome commit together.
"""

from collections import defaultdict

_HOOKS: dict[str, list] = defaultdict(list)


def on_decision(policy_key: str):
    def deco(fn):
        _HOOKS[policy_key].append(fn)
        return fn
    return deco


def fire(req, outcome: str) -> None:
    for fn in _HOOKS.get(req.policy.key, ()):
        fn(req, outcome)
