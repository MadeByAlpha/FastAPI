import email.message
import errno
import os
import stat
import warnings
from contextlib import AsyncExitStack, asynccontextmanager

from starlette._utils import get_route_path
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import URL
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import BaseRoute, Match, NoMatchFound
from starlette.staticfiles import StaticFiles

from fastapi.dependencies.utils import solve_dependencies
from fastapi.exceptions import RequestValidationError

from ._handlers import _build_dependant_with_parameterless_dependencies
from ._scope import (
    _FASTAPI_FRONTEND_PATH_KEY,
    _FASTAPI_FRONTEND_SPECIFICITY_KEY,
    _FASTAPI_SCOPE_KEY,
    _SCOPE_MISSING,
    _get_fastapi_scope,
    _get_scope_effective_route_context,
    _update_scope,
)

if __debug__ and __import__("typing").TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Sequence
    from typing import Any, Literal

    from starlette.datastructures import URLPath
    from starlette.responses import Response
    from starlette.types import Receive, Scope, Send

    from fastapi import params
    from fastapi.dependencies.models import Dependant
    from fastapi.dependencies.utils import SolvedDependency

    __all__ = (
        "_FrontendRoute",
        "_FrontendRouteGroup",
        "_FrontendStaticFiles",
        "_frontend_dependency_endpoint",
        "_frontend_path_specificity",
        "_join_frontend_paths",
        "_normalize_frontend_path",
        "_resolve_frontend_check_dir",
    )


def _frontend_dependency_endpoint() -> None:
    pass  # pragma: no cover


def _normalize_frontend_path(path: str) -> str:
    if not path:
        raise AssertionError("A frontend path cannot be empty")
    if not path.startswith("/"):
        raise AssertionError("A frontend path must start with '/'")
    if path != "/":
        path = path.rstrip("/")
    return path


def _join_frontend_paths(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if path == "/":
        return prefix
    return prefix + path


def _frontend_path_specificity(path: str) -> int:
    if path == "/":
        return 0
    return len(path)


def _get_resolved_absolute_path(path: str | os.PathLike[str]) -> str:
    return os.path.realpath(os.fspath(path))


def _resolve_frontend_check_dir(
    *,
    directory: str | os.PathLike[str],
    check_dir: bool | Literal["auto"],
) -> bool:
    if check_dir != "auto":
        return check_dir
    if os.environ.get("FASTAPI_ENV") != "development":
        return True
    if not os.path.isdir(directory):
        warnings.warn(
            f"Frontend directory '{directory}' does not exist. "
            f"Resolved absolute path: '{_get_resolved_absolute_path(directory)}'",
            stacklevel=3,
        )
    return False


class _FrontendStaticFiles(StaticFiles):
    def __init__(
        self,
        *,
        directory: str | os.PathLike[str],
        fallback: Literal["auto", "index.html", "404.html"] | None,
        check_dir: bool,
    ) -> None:
        self.fallback = fallback
        if check_dir and not os.path.isdir(directory):
            raise RuntimeError(
                f"Frontend directory '{directory}' does not exist. "
                f"Resolved absolute path: '{_get_resolved_absolute_path(directory)}'"
            )
        super().__init__(
            directory=directory,
            html=True,
            check_dir=check_dir,
            follow_symlink=False,
        )
        if check_dir and fallback in {"index.html", "404.html"}:
            self._check_fallback_file(fallback)

    def _check_fallback_file(self, fallback: str) -> None:
        _, stat_result = self.lookup_path(fallback)
        if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            raise RuntimeError(
                f"Frontend fallback file '{fallback}' does not exist in "
                f"directory '{self.directory}'. Resolved absolute directory: "
                f"'{self._get_resolved_directory()}'"
            )

    def _get_resolved_directory(self) -> str:
        assert self.directory is not None
        return _get_resolved_absolute_path(self.directory)

    def get_path(self, scope: Scope) -> str:
        path = _get_fastapi_scope(scope).get(_FASTAPI_FRONTEND_PATH_KEY, "")
        assert isinstance(path, str)
        return os.path.normpath(os.path.join(*path.split("/")))

    async def get_response_for_scope(self, scope: Scope) -> Response:
        if not self.config_checked:
            await self.check_config()
            self.config_checked = True
        return await self.get_response(self.get_path(scope), scope)

    async def get_response(self, path: str, scope: Scope) -> Response:
        if scope["method"] not in ("GET", "HEAD"):
            if await self._lookup_static_resource(path) is not None:
                raise HTTPException(status_code=405)
            raise HTTPException(status_code=404)

        static_resource = await self._lookup_static_resource(path)
        if static_resource is not None:
            full_path, stat_result, is_directory_index = static_resource
            if is_directory_index and not scope["path"].endswith("/"):
                url = URL(scope=scope)
                url = url.replace(path=url.path + "/")
                return RedirectResponse(url=url)
            return self.file_response(full_path, stat_result, scope)

        if self.fallback == "404.html" or (self.fallback == "auto" and self._fallback_file_exists("404.html")):
            return await self._fallback_response("404.html", scope, status_code=404)

        if (
            self.fallback == "index.html" or (self.fallback == "auto" and self._fallback_file_exists("index.html"))
        ) and _is_frontend_navigation_request(scope):
            return await self._fallback_response("index.html", scope, status_code=200)

        raise HTTPException(status_code=404)

    async def _lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        try:
            return await run_in_threadpool(self.lookup_path, path)
        except PermissionError:
            raise HTTPException(status_code=401) from None
        except OSError as exc:
            if exc.errno == errno.ENAMETOOLONG:
                raise HTTPException(status_code=404) from None
            raise exc
        except ValueError:
            raise HTTPException(status_code=404) from None

    async def _lookup_static_resource(self, path: str) -> tuple[str, os.stat_result, bool] | None:
        full_path, stat_result = await self._lookup_path(path)
        if stat_result is None:
            return None
        if stat.S_ISREG(stat_result.st_mode):
            return full_path, stat_result, False
        if stat.S_ISDIR(stat_result.st_mode):
            index_path = os.path.join(path, "index.html")
            full_path, stat_result = await self._lookup_path(index_path)
            if stat_result is not None and stat.S_ISREG(stat_result.st_mode):
                return full_path, stat_result, True
        return None

    def _fallback_file_exists(self, fallback: str) -> bool:
        _, stat_result = self.lookup_path(fallback)
        return stat_result is not None and stat.S_ISREG(stat_result.st_mode)

    async def _fallback_response(self, fallback: str, scope: Scope, *, status_code: int) -> Response:
        full_path, stat_result = await run_in_threadpool(self.lookup_path, fallback)
        if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            raise RuntimeError(
                f"Frontend fallback file '{fallback}' does not exist in "
                f"directory '{self.directory}'. Resolved absolute directory: "
                f"'{self._get_resolved_directory()}'"
            )
        return self.file_response(full_path, stat_result, scope, status_code=status_code)


def _iter_accept_media_types(accept: str) -> Iterator[tuple[str, float]]:
    for raw_value in accept.split(","):
        message = email.message.Message()
        message["content-type"] = raw_value.strip()
        q = message.get_param("q")
        quality = 1.0
        if isinstance(q, str):
            try:
                quality = float(q)
            except ValueError:
                pass
        yield (
            f"{message.get_content_maintype()}/{message.get_content_subtype()}",
            quality,
        )


def _is_frontend_navigation_request(scope: Scope) -> bool:
    request = Request(scope)
    for media_type, quality in _iter_accept_media_types(request.headers.get("accept", "")):
        if media_type in {"text/html", "application/xhtml+xml"} and quality != 0:
            return True
    return False


class _FrontendRoute(BaseRoute):
    def __init__(
        self,
        path: str,
        *,
        directory: str | os.PathLike[str],
        fallback: Literal["auto", "index.html", "404.html"] | None = "auto",
        check_dir: bool,
    ) -> None:
        if fallback not in {"auto", "index.html", "404.html", None}:
            raise AssertionError("fallback must be 'auto', 'index.html', '404.html', or None")
        self.path = _normalize_frontend_path(path)
        self.methods = {"GET", "HEAD"}
        self.app = _FrontendStaticFiles(directory=directory, fallback=fallback, check_dir=check_dir)

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        return self.matches_with_path(scope, self.path)

    def matches_with_path(self, scope: Scope, path: str) -> tuple[Match, Scope]:
        if scope["type"] != "http":
            return Match.NONE, {}
        frontend_path = self._get_frontend_path(path, get_route_path(scope))
        if frontend_path is None:
            return Match.NONE, {}
        child_scope = {
            _FASTAPI_SCOPE_KEY: {
                _FASTAPI_FRONTEND_PATH_KEY: frontend_path,
                _FASTAPI_FRONTEND_SPECIFICITY_KEY: _frontend_path_specificity(path),
            }
        }
        if scope["method"] not in self.methods:
            return Match.PARTIAL, child_scope
        return Match.FULL, child_scope

    def _get_frontend_path(self, path: str, route_path: str) -> str | None:
        if path == "/":
            return route_path.lstrip("/")
        if route_path == path:
            return ""
        prefix = path + "/"
        if route_path.startswith(prefix):
            return route_path[len(prefix) :]
        return None

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = await self.app.get_response_for_scope(scope)
        await response(scope, receive, send)

    def url_path_for(self, name: str, /, **path_params: Any) -> URLPath:
        raise NoMatchFound(name, path_params)


class _FrontendRouteGroup(BaseRoute):
    def __init__(
        self,
        *,
        dependencies: Sequence[params.Depends] | None = None,
        dependency_overrides_provider: Any | None = None,
    ) -> None:
        self.routes: list[_FrontendRoute] = []
        self.dependencies = list(dependencies or [])
        self.dependency_overrides_provider = dependency_overrides_provider
        (
            self.dependant,
            _,
            self._embed_body_fields,
        ) = _build_dependant_with_parameterless_dependencies(
            path="",
            call=_frontend_dependency_endpoint,
            dependencies=self.dependencies,
        )

    def add_frontend_route(
        self,
        path: str,
        *,
        directory: str | os.PathLike[str],
        fallback: Literal["auto", "index.html", "404.html"] | None = "auto",
        check_dir: bool,
    ) -> None:
        self.routes.append(
            _FrontendRoute(
                path,
                directory=directory,
                fallback=fallback,
                check_dir=check_dir,
            )
        )

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope, _ = self._match(scope, prefix="")
        return match, child_scope

    def matches_with_prefix(self, scope: Scope, prefix: str) -> tuple[Match, Scope]:
        match, child_scope, _ = self._match(scope, prefix=prefix)
        return match, child_scope

    def _match(self, scope: Scope, *, prefix: str) -> tuple[Match, Scope, _FrontendRoute | None]:
        full: tuple[Scope, _FrontendRoute, int] | None = None
        partial: tuple[Scope, _FrontendRoute, int] | None = None
        for route in self.routes:
            path = _join_frontend_paths(prefix, route.path)
            match, child_scope = route.matches_with_path(scope, path)
            specificity = _frontend_path_specificity(path)
            if match == Match.FULL:
                if full is None or specificity > full[2]:
                    full = (child_scope, route, specificity)
            elif match == Match.PARTIAL:
                if partial is None or specificity > partial[2]:
                    partial = (child_scope, route, specificity)
        if full is not None:
            child_scope, route, _ = full
            return Match.FULL, child_scope, route
        if partial is not None:
            child_scope, route, _ = partial
            return Match.PARTIAL, child_scope, route
        return Match.NONE, {}, None

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        from ._include import _EffectiveRouteContext

        effective_context = _get_scope_effective_route_context(scope)
        if isinstance(effective_context, _EffectiveRouteContext) and effective_context.original_route is self:
            prefix = effective_context.frontend_prefix
            dependant = effective_context.dependant
            dependency_overrides_provider = effective_context.dependency_overrides_provider
            embed_body_fields = effective_context._embed_body_fields
        else:
            prefix = ""
            dependant = self.dependant
            dependency_overrides_provider = self.dependency_overrides_provider
            embed_body_fields = self._embed_body_fields
        match, child_scope, route = self._match(scope, prefix=prefix)
        if match == Match.NONE or route is None:
            raise HTTPException(status_code=404)
        _update_scope(scope, child_scope)
        if match == Match.FULL and dependant and dependant.dependencies:
            async with self._solve_dependencies(
                scope,
                receive,
                send,
                dependant=dependant,
                dependency_overrides_provider=dependency_overrides_provider,
                embed_body_fields=embed_body_fields,
            ) as solved_result:
                response = await route.app.get_response_for_scope(scope)
                if response.background is None:
                    response.background = solved_result.background_tasks
                response.headers.raw.extend(solved_result.response.headers.raw)
                await response(scope, receive, send)
            return
        await route.handle(scope, receive, send)

    def url_path_for(self, name: str, /, **path_params: Any) -> URLPath:
        raise NoMatchFound(name, path_params)

    # TODO: probably move this out of the Route / Route Group, same in APIRoute
    # this should probably be top level FastAPI logic, not part of APIRoute and
    # duplicated here
    @asynccontextmanager
    async def _solve_dependencies(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        dependant: Dependant,
        dependency_overrides_provider: Any | None,
        embed_body_fields: bool,
    ) -> AsyncIterator[SolvedDependency]:
        request = Request(scope, receive, send)
        previous_inner_astack = scope.get("fastapi_inner_astack", _SCOPE_MISSING)
        previous_function_astack = scope.get("fastapi_function_astack", _SCOPE_MISSING)
        try:
            async with AsyncExitStack() as request_stack:
                scope["fastapi_inner_astack"] = request_stack
                async with AsyncExitStack() as function_stack:
                    scope["fastapi_function_astack"] = function_stack
                    solved_result = await solve_dependencies(
                        request=request,
                        dependant=dependant,
                        dependency_overrides_provider=dependency_overrides_provider,
                        async_exit_stack=request_stack,
                        embed_body_fields=embed_body_fields,
                    )
                    if solved_result.errors:
                        raise RequestValidationError(solved_result.errors)
                    yield solved_result
        finally:
            if previous_inner_astack is _SCOPE_MISSING:
                scope.pop("fastapi_inner_astack", None)
            else:
                scope["fastapi_inner_astack"] = previous_inner_astack
            if previous_function_astack is _SCOPE_MISSING:
                scope.pop("fastapi_function_astack", None)
            else:
                scope["fastapi_function_astack"] = previous_function_astack
