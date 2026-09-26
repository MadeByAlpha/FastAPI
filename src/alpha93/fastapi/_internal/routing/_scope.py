from contextvars import ContextVar

if __debug__ and __import__("typing").TYPE_CHECKING:
    from typing import Any

    from starlette.types import Scope

    __all__ = (
        "_FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY",
        "_FASTAPI_FRONTEND_PATH_KEY",
        "_FASTAPI_FRONTEND_SPECIFICITY_KEY",
        "_FASTAPI_INCLUDED_ROUTER_KEY",
        "_FASTAPI_SCOPE_KEY",
        "_SCOPE_MISSING",
        "_effective_route_context_var",
        "_frontend_scope_specificity",
        "_get_fastapi_scope",
        "_get_scope_effective_route_context",
        "_get_scope_included_router",
        "_restore_fastapi_scope_key",
        "_update_scope",
    )


_FASTAPI_SCOPE_KEY = "fastapi"
_FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY = "effective_route_context"
_FASTAPI_FRONTEND_PATH_KEY = "frontend_path"
_FASTAPI_FRONTEND_SPECIFICITY_KEY = "frontend_specificity"
_FASTAPI_INCLUDED_ROUTER_KEY = "included_router"
_effective_route_context_var: ContextVar[Any | None] = ContextVar("fastapi_effective_route_context", default=None)
_SCOPE_MISSING = object()


def _get_fastapi_scope(scope: Scope) -> dict[str, Any]:
    fastapi_scope = scope.setdefault(_FASTAPI_SCOPE_KEY, {})
    assert isinstance(fastapi_scope, dict)
    return fastapi_scope


def _update_scope(scope: Scope, child_scope: Scope) -> None:
    fastapi_child_scope = child_scope.get(_FASTAPI_SCOPE_KEY)
    for key, value in child_scope.items():
        if key != _FASTAPI_SCOPE_KEY:
            scope[key] = value
    if isinstance(fastapi_child_scope, dict):
        _get_fastapi_scope(scope).update(fastapi_child_scope)


def _get_scope_effective_route_context(scope: Scope) -> Any | None:
    return scope.get(_FASTAPI_SCOPE_KEY, {}).get(_FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY)


def _get_scope_included_router(scope: Scope) -> Any | None:
    return scope.get(_FASTAPI_SCOPE_KEY, {}).get(_FASTAPI_INCLUDED_ROUTER_KEY)


def _frontend_scope_specificity(scope: Scope) -> int | None:
    specificity = scope.get(_FASTAPI_SCOPE_KEY, {}).get(_FASTAPI_FRONTEND_SPECIFICITY_KEY)
    if isinstance(specificity, int):
        return specificity
    return None


def _restore_fastapi_scope_key(scope: Scope, key: str, previous: Any) -> None:
    fastapi_scope = scope.get(_FASTAPI_SCOPE_KEY)
    if not isinstance(fastapi_scope, dict):
        return
    if previous is _SCOPE_MISSING:
        fastapi_scope.pop(key, None)
    else:
        fastapi_scope[key] = previous
