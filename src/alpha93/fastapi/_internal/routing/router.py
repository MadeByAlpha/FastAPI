import inspect
from contextlib import asynccontextmanager
from warnings import deprecated

from starlette._utils import get_route_path, is_async_callable
from starlette.datastructures import URL
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Match, Router

from fastapi.datastructures import Default
from fastapi.exceptions import FastAPIError
from fastapi.utils import generate_unique_id, get_value_or_default

from ._include import _EffectiveRouteContext, _IncludedRouter, _iter_routes_with_context, _RouterIncludeContext
from ._lifespan import _DefaultLifespan, _merge_lifespan_context, _wrap_gen_lifespan_context
from ._scope import (
    _FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY,
    _SCOPE_MISSING,
    _frontend_scope_specificity,
    _get_fastapi_scope,
    _get_scope_included_router,
    _restore_fastapi_scope_key,
    _update_scope,
)
from .frontend import _FrontendRouteGroup, _join_frontend_paths, _normalize_frontend_path, _resolve_frontend_check_dir
from .routes import APIRoute, APIWebSocketRoute

if __debug__ and __import__("typing").TYPE_CHECKING:
    import os
    from collections.abc import Awaitable, Callable, Collection, Iterator, Sequence
    from enum import Enum
    from typing import Annotated, Any, Literal

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import BaseRoute
    from starlette.types import ASGIApp, Lifespan, Receive, Scope, Send
    from starlette.websockets import WebSocket

    from fastapi import params
    from fastapi.datastructures import DefaultPlaceholder
    from fastapi.types import DecoratedCallable, IncEx

    __all__ = ("APIRouter",)


class APIRouter(Router):
    """
    `APIRouter` class, used to group *path operations*, for example to structure
    an app in multiple files. It would then be included in the `FastAPI` app, or
    in another `APIRouter` (ultimately included in the app).

    Read more about it in the
    [FastAPI docs for Bigger Applications - Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

    ## Example

    ```python
    from fastapi import APIRouter, FastAPI

    app = FastAPI()
    router = APIRouter()


    @router.get("/users/", tags=["users"])
    async def read_users():
        return [{"username": "Rick"}, {"username": "Morty"}]


    app.include_router(router)
    ```
    """

    def __init__(
        self,
        *,
        prefix: str = "",
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        default_response_class: type[Response] = Default(JSONResponse),
        responses: dict[int | str, dict[str, Any]] | None = None,
        callbacks: list[BaseRoute] | None = None,
        routes: Annotated[
            list[BaseRoute] | None,
            deprecated(
                """
                You normally wouldn't use this parameter with FastAPI, it is inherited
                from Starlette and supported for compatibility.

                In FastAPI, you normally would use the *path operation methods*,
                like `router.get()`, `router.post()`, etc.
                """
            ),
        ] = None,
        redirect_slashes: bool = True,
        default: ASGIApp | None = None,
        dependency_overrides_provider: Any | None = None,
        route_class: type[APIRoute] = APIRoute,
        on_startup: Sequence[Callable[[], Any]] | None = None,
        on_shutdown: Sequence[Callable[[], Any]] | None = None,
        # the generic to Lifespan[AppType] is the type of the top level application
        # which the router cannot know statically, so we use typing.Any
        lifespan: Lifespan[Any] | None = None,
        deprecated: bool | None = None,
        include_in_schema: bool = True,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
        strict_content_type: bool = Default(True),
    ) -> None:
        # Determine the lifespan context to use
        """
        Args:
            prefix: An optional path prefix for the router.

            tags: A list of tags to be applied to all the *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            dependencies: A list of dependencies (using `Depends()`) to be applied to all the
                *path operations* in this router.

                Read more about it in the
                [FastAPI docs for Bigger Applications - Multiple
                Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies).

            default_response_class: The default response class to be used.

                Read more in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#default-response-class).

            responses: Additional responses to be shown in OpenAPI.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Additional Responses in
                OpenAPI](https://fastapi.tiangolo.com/advanced/additional-responses/).

                And in the
                [FastAPI docs for Bigger
                Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies).

            callbacks: OpenAPI callbacks that should apply to all *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            routes: **Note**: you probably shouldn't use this parameter, it is inherited
                from Starlette and supported for compatibility.

                ---

                A list of routes to serve incoming HTTP and WebSocket requests.

            redirect_slashes: Whether to detect and redirect slashes in URLs when the client doesn't
                use the same format.

            default: Default function handler for this router. Used to handle
                404 Not Found errors.

            dependency_overrides_provider: Only used internally by FastAPI to handle dependency overrides.

                You shouldn't need to use it. It normally points to the `FastAPI` app
                object.

            route_class: Custom route (*path operation*) class to be used by this router.

                Read more about it in the
                [FastAPI docs for Custom Request and APIRoute
                class](https://fastapi.tiangolo.com/how-to/custom-request-and-route/#custom-apiroute-class-in-a-router).

            on_startup: A list of startup event handler functions.

                You should instead use the `lifespan` handlers.

                Read more in the [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).

            on_shutdown: A list of shutdown event handler functions.

                You should instead use the `lifespan` handlers.

                Read more in the
                [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).

            lifespan: A `Lifespan` context manager handler. This replaces `startup` and
                `shutdown` functions with a single context manager.

                Read more in the
                [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).

            deprecated: Mark all *path operations* in this router as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            include_in_schema: To include (or not) all the *path operations* in this router in the
                generated OpenAPI.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            strict_content_type: Enable strict checking for request Content-Type headers.

                When `True` (the default), requests with a body that do not include
                a `Content-Type` header will **not** be parsed as JSON.

                This prevents potential cross-site request forgery (CSRF) attacks
                that exploit the browser's ability to send requests without a
                Content-Type header, bypassing CORS preflight checks. In particular
                applicable for apps that need to be run locally (in localhost).

                When `False`, requests without a `Content-Type` header will have
                their body parsed as JSON, which maintains compatibility with
                certain clients that don't send `Content-Type` headers.

                Read more about it in the
                [FastAPI docs for Strict Content-Type](https://fastapi.tiangolo.com/advanced/strict-content-type/).
        """
        if lifespan is None:
            # Use the default lifespan that runs on_startup/on_shutdown handlers
            lifespan_context: Lifespan[Any] = _DefaultLifespan(self)
        elif inspect.isasyncgenfunction(lifespan):
            lifespan_context = asynccontextmanager(lifespan)
        elif inspect.isgeneratorfunction(lifespan):
            lifespan_context = _wrap_gen_lifespan_context(lifespan)
        else:
            lifespan_context = lifespan
        self.lifespan_context = lifespan_context

        super().__init__(
            routes=routes,
            redirect_slashes=redirect_slashes,
            default=default,
            lifespan=lifespan_context,
        )
        if prefix:
            assert prefix.startswith("/"), "A path prefix must start with '/'"
            assert not prefix.endswith("/"), "A path prefix must not end with '/', as the routes will start with '/'"

        # Handle on_startup/on_shutdown locally since Starlette removed support
        # Ref: https://github.com/Kludex/starlette/pull/3117
        # TODO: deprecate this once the lifespan (or alternative) interface is improved
        self.on_startup: list[Callable[[], Any]] = [] if on_startup is None else list(on_startup)
        self.on_shutdown: list[Callable[[], Any]] = [] if on_shutdown is None else list(on_shutdown)

        self.prefix = prefix
        self.tags: list[str | Enum] = tags or []
        self.dependencies = list(dependencies or [])
        self.deprecated = deprecated
        self.include_in_schema = include_in_schema
        self.responses = responses or {}
        self.callbacks = callbacks or []
        self.dependency_overrides_provider = dependency_overrides_provider
        self.route_class = route_class
        self.default_response_class = default_response_class
        self.generate_unique_id_function = generate_unique_id_function
        self.strict_content_type = strict_content_type
        self._routes_version = 0
        self._low_priority_routes: list[BaseRoute] = []
        self._frontend_routes: _FrontendRouteGroup | None = None

    def _mark_routes_changed(self) -> None:
        self._routes_version += 1

    def _get_routes_version(self, seen: set[int] | None = None) -> int:
        if seen is None:
            seen = set()
        router_id = id(self)
        if router_id in seen:
            return self._routes_version
        seen.add(router_id)
        version = self._routes_version
        for route in self.routes:
            if isinstance(route, _IncludedRouter):
                version += route.original_router._get_routes_version(seen)
        return version

    def _contains_router(self, router: "APIRouter", seen: set[int] | None = None) -> bool:
        if seen is None:
            seen = set()
        router_id = id(self)
        if router_id in seen:
            return False
        seen.add(router_id)
        for route in self.routes:
            if not isinstance(route, _IncludedRouter):
                continue
            if route.original_router is router:
                return True
            if route.original_router._contains_router(router, seen):
                return True
        return False

    def add_route(
        self,
        path: str,
        endpoint: Callable[[Request], Awaitable[Response] | Response],
        methods: Collection[str] | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
    ) -> None:
        super().add_route(
            path,
            endpoint,
            methods=methods,
            name=name,
            include_in_schema=include_in_schema,
        )
        self._mark_routes_changed()

    def add_websocket_route(
        self,
        path: str,
        endpoint: Callable[[WebSocket], Awaitable[None]],
        name: str | None = None,
    ) -> None:
        super().add_websocket_route(path, endpoint, name=name)
        self._mark_routes_changed()

    def frontend(
        self,
        path: str,
        *,
        directory: str | os.PathLike[str],
        fallback: Literal["auto", "index.html", "404.html"] | None = "auto",
        check_dir: bool | Literal["auto"] = "auto",
    ) -> None:
        """
        Serve a static frontend build as low-priority routes.

        Use this for frontend tools that build static files into a directory,
        such as `dist`. **FastAPI** path operations are checked first, and
        the frontend files are checked only if no normal route matched.

        A typical project could look like this:

        ```text
        .
        ├── pyproject.toml
        ├── app
        │   ├── __init__.py
        │   └── main.py
        └── dist
            ├── index.html
            └── assets
                └── app.js
        ```

        Then in `app/main.py`:

        ```python
        from fastapi import APIRouter, FastAPI

        app = FastAPI()
        router = APIRouter()
        router.frontend("/", directory="dist")
        app.include_router(router)
        ```

        Args:
            path: The URL path prefix where the frontend build should be served.

            directory: The directory containing the static frontend build output.

            fallback: The fallback file behavior for missing frontend paths.

            check_dir: Check that the frontend directory exists when the app is created. When
                set to `"auto"`, skip the check with a warning when `FASTAPI_ENV` is
                `"development"`, and check it otherwise. The `fastapi dev` command
                sets `FASTAPI_ENV` to `"development"` if it is not already set.
        """
        check_dir = _resolve_frontend_check_dir(directory=directory, check_dir=check_dir)
        normalized_path = _normalize_frontend_path(path)
        if self._frontend_routes is None:
            self._frontend_routes = _FrontendRouteGroup(
                dependencies=self.dependencies,
                dependency_overrides_provider=self.dependency_overrides_provider,
            )
            self._low_priority_routes.append(self._frontend_routes)
        self._frontend_routes.add_frontend_route(
            _join_frontend_paths(self.prefix, normalized_path),
            directory=directory,
            fallback=fallback,
            check_dir=check_dir,
        )
        self._mark_routes_changed()

    async def app(self, scope: Scope, receive: Receive, send: Send) -> None:
        assert scope["type"] in ("http", "websocket", "lifespan")

        if "router" not in scope:
            scope["router"] = self

        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
            return

        partial: tuple[BaseRoute, Scope] | None = None
        for route in self.routes:
            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                scope.update(child_scope)
                await route.handle(scope, receive, send)
                return
            if match == Match.PARTIAL and partial is None:
                partial = (route, child_scope)

        if partial is not None:
            route, child_scope = partial
            scope.update(child_scope)
            await route.handle(scope, receive, send)
            return

        route_path = get_route_path(scope)
        if scope["type"] == "http" and self.redirect_slashes and route_path != "/":
            redirect_scope = dict(scope)
            if route_path.endswith("/"):
                redirect_scope["path"] = redirect_scope["path"].rstrip("/")
            else:
                redirect_scope["path"] = redirect_scope["path"] + "/"

            for route in self.routes:
                match, _ = route.matches(redirect_scope)
                if match != Match.NONE:
                    redirect_url = URL(scope=redirect_scope)
                    response = RedirectResponse(url=str(redirect_url))
                    await response(scope, receive, send)
                    return

        (
            low_priority_match,
            low_priority_scope,
            low_priority_route,
            low_priority_context,
        ) = self._match_low_priority(scope)
        if low_priority_match != Match.NONE and low_priority_route is not None:
            _update_scope(scope, low_priority_scope)
            if low_priority_context is not None:
                _get_fastapi_scope(scope)[_FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY] = low_priority_context
                original_route = low_priority_context.original_route
                if isinstance(original_route, APIRoute):
                    scope["route"] = original_route
                    await original_route.handle(scope, receive, send)
                    return
            await low_priority_route.handle(scope, receive, send)
            return

        await self.default(scope, receive, send)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        included_router = _get_scope_included_router(scope)
        if isinstance(included_router, _IncludedRouter) and included_router.original_router is self:
            await included_router._handle_selected(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        included_router = _get_scope_included_router(scope)
        if isinstance(included_router, _IncludedRouter) and included_router.original_router is self:
            match, child_scope, _, _ = included_router._match(scope)
            return match, child_scope
        return Match.NONE, {}

    def _iter_low_priority_routes(
        self,
    ) -> Iterator[BaseRoute | _EffectiveRouteContext]:
        yield from self._low_priority_routes
        for route in self.routes:
            if isinstance(route, _IncludedRouter):
                yield from route.effective_low_priority_routes()

    def _match_low_priority(self, scope: Scope) -> tuple[Match, Scope, BaseRoute | None, _EffectiveRouteContext | None]:
        full: tuple[Scope, BaseRoute, _EffectiveRouteContext | None] | None = None
        partial: tuple[Scope, BaseRoute, _EffectiveRouteContext | None] | None = None
        for candidate in self._iter_low_priority_routes():
            route: BaseRoute
            if isinstance(candidate, _EffectiveRouteContext):
                route_context: _EffectiveRouteContext | None = candidate
                original_route = candidate.original_route
                if isinstance(original_route, APIRoute):
                    fastapi_scope = _get_fastapi_scope(scope)
                    previous_context = fastapi_scope.get(_FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY, _SCOPE_MISSING)
                    fastapi_scope[_FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY] = route_context
                    try:
                        match, child_scope = original_route.matches(scope)
                    finally:
                        _restore_fastapi_scope_key(
                            scope,
                            _FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY,
                            previous_context,
                        )
                    route = original_route
                else:
                    match, child_scope = candidate.matches(scope)
                    route = candidate.starlette_route or original_route
            else:
                route_context = None
                match, child_scope = candidate.matches(scope)
                route = candidate
            if match == Match.FULL:
                if full is None or self._frontend_match_is_more_specific(child_scope, full[0]):
                    full = (child_scope, route, route_context)
            elif match == Match.PARTIAL:
                if partial is None or self._frontend_match_is_more_specific(child_scope, partial[0]):
                    partial = (child_scope, route, route_context)
        if full is not None:
            child_scope, route, route_context = full
            return Match.FULL, child_scope, route, route_context
        if partial is not None:
            child_scope, route, route_context = partial
            return Match.PARTIAL, child_scope, route, route_context
        return Match.NONE, {}, None, None

    def _frontend_match_is_more_specific(self, child_scope: Scope, previous_child_scope: Scope) -> bool:
        specificity = _frontend_scope_specificity(child_scope)
        previous_specificity = _frontend_scope_specificity(previous_child_scope)
        if specificity is None or previous_specificity is None:
            return False
        return specificity > previous_specificity

    def route(
        self,
        path: str,
        methods: Collection[str] | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            self.add_route(
                path,
                func,
                methods=methods,
                name=name,
                include_in_schema=include_in_schema,
            )
            return func

        return decorator

    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        methods: set[str] | list[str] | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] | DefaultPlaceholder = Default(JSONResponse),
        name: str | None = None,
        route_class_override: type[APIRoute] | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] | DefaultPlaceholder = Default(generate_unique_id),
        strict_content_type: bool | DefaultPlaceholder = Default(True),
    ) -> None:
        route_class = route_class_override or self.route_class
        responses = responses or {}
        combined_responses = {**self.responses, **responses}
        current_response_class = get_value_or_default(response_class, self.default_response_class)
        current_tags = self.tags.copy()
        if tags:
            current_tags.extend(tags)
        current_dependencies = self.dependencies.copy()
        if dependencies:
            current_dependencies.extend(dependencies)
        current_callbacks = self.callbacks.copy()
        if callbacks:
            current_callbacks.extend(callbacks)
        current_generate_unique_id = get_value_or_default(generate_unique_id_function, self.generate_unique_id_function)
        route = route_class(
            self.prefix + path,
            endpoint=endpoint,
            response_model=response_model,
            status_code=status_code,
            tags=current_tags,
            dependencies=current_dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=combined_responses,
            deprecated=deprecated or self.deprecated,
            methods=methods,
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema and self.include_in_schema,
            response_class=current_response_class,
            name=name,
            dependency_overrides_provider=self.dependency_overrides_provider,
            callbacks=current_callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=current_generate_unique_id,
            strict_content_type=get_value_or_default(strict_content_type, self.strict_content_type),
        )
        self.routes.append(route)
        self._mark_routes_changed()

    def api_route(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        methods: list[str] | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            self.add_api_route(
                path,
                func,
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                methods=methods,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            )
            return func

        return decorator

    def add_api_websocket_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str | None = None,
        *,
        dependencies: Sequence[params.Depends] | None = None,
    ) -> None:
        current_dependencies = self.dependencies.copy()
        if dependencies:
            current_dependencies.extend(dependencies)

        route = APIWebSocketRoute(
            self.prefix + path,
            endpoint=endpoint,
            name=name,
            dependencies=current_dependencies,
            dependency_overrides_provider=self.dependency_overrides_provider,
        )
        self.routes.append(route)
        self._mark_routes_changed()

    def websocket(
        self,
        path: str,
        name: str | None = None,
        *,
        dependencies: Sequence[params.Depends] | None = None,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Decorate a WebSocket function.

        Read more about it in the
        [FastAPI docs for WebSockets](https://fastapi.tiangolo.com/advanced/websockets/).

        **Example**

        Args:
            path: WebSocket path.

            name: A name for the WebSocket. Only used internally.

            dependencies: A list of dependencies (using `Depends()`) to be used for this
                WebSocket.

                Read more about it in the
                [FastAPI docs for WebSockets](https://fastapi.tiangolo.com/advanced/websockets/).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI, WebSocket

        app = FastAPI()
        router = APIRouter()

        @router.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            while True:
                data = await websocket.receive_text()
                await websocket.send_text(f"Message text was: {data}")

        app.include_router(router)
        ```
        """

        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            self.add_api_websocket_route(path, func, name=name, dependencies=dependencies)
            return func

        return decorator

    def websocket_route(self, path: str, name: str | None = None) -> Callable[[DecoratedCallable], DecoratedCallable]:
        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            self.add_websocket_route(path, func, name=name)
            return func

        return decorator

    def include_router(
        self,
        router: "APIRouter",
        *,
        prefix: str = "",
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        default_response_class: type[Response] = Default(JSONResponse),
        responses: dict[int | str, dict[str, Any]] | None = None,
        callbacks: list[BaseRoute] | None = None,
        deprecated: bool | None = None,
        include_in_schema: bool = True,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> None:
        """
        Include another `APIRouter` in the same current `APIRouter`.

        Read more about it in the
        [FastAPI docs for Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

        Args:
            router: The `APIRouter` to include.

            prefix: An optional path prefix for the router.

            tags: A list of tags to be applied to all the *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            dependencies: A list of dependencies (using `Depends()`) to be applied to all the
                *path operations* in this router.

                Read more about it in the
                [FastAPI docs for Bigger Applications - Multiple
                Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies).

            default_response_class: The default response class to be used.

                Read more in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#default-response-class).

            responses: Additional responses to be shown in OpenAPI.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Additional Responses in
                OpenAPI](https://fastapi.tiangolo.com/advanced/additional-responses/).

                And in the
                [FastAPI docs for Bigger
                Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies).

            callbacks: OpenAPI callbacks that should apply to all *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            deprecated: Mark all *path operations* in this router as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            include_in_schema: Include (or not) all the *path operations* in this router in the
                generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI

        app = FastAPI()
        internal_router = APIRouter()
        users_router = APIRouter()

        @users_router.get("/users/")
        def read_users():
            return [{"name": "Rick"}, {"name": "Morty"}]

        internal_router.include_router(users_router)
        app.include_router(internal_router)
        ```
        """
        assert self is not router, (
            "Cannot include the same APIRouter instance into itself. Did you mean to include a different router?"
        )
        assert not router._contains_router(self), (
            "Cannot include an APIRouter instance that already includes this router. "
            "Did you mean to include a different router?"
        )
        if prefix:
            assert prefix.startswith("/"), "A path prefix must start with '/'"
            assert not prefix.endswith("/"), "A path prefix must not end with '/', as the routes will start with '/'"
        else:
            for route, route_context in _iter_routes_with_context(router.routes):
                if route_context is None:
                    path = getattr(route, "path", None)
                    name = getattr(route, "name", "unknown")
                elif route_context.starlette_route is not None:
                    path = getattr(route_context.starlette_route, "path", None)
                    name = getattr(route_context.starlette_route, "name", "unknown")
                else:
                    path = route_context.path
                    name = route_context.name
                if path is not None and not path:
                    raise FastAPIError(f"Prefix and path cannot be both empty (path operation: {name})")
        include_context = _RouterIncludeContext.for_include(
            parent_router=self,
            included_router=router,
            prefix=prefix,
            tags=tags,
            dependencies=dependencies,
            default_response_class=default_response_class,
            responses=responses,
            callbacks=callbacks,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            generate_unique_id_function=generate_unique_id_function,
        )
        self.routes.append(_IncludedRouter(original_router=router, include_context=include_context))
        self._mark_routes_changed()
        for handler in router.on_startup:
            self.add_event_handler("startup", handler)
        for handler in router.on_shutdown:
            self.add_event_handler("shutdown", handler)
        self.lifespan_context = _merge_lifespan_context(
            self.lifespan_context,
            router.lifespan_context,
        )

    def get(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP GET operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI

        app = FastAPI()
        router = APIRouter()

        @router.get("/items/")
        def read_items():
            return [{"name": "Empanada"}, {"name": "Arepa"}]

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["GET"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def put(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP PUT operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            description: str | None = None

        app = FastAPI()
        router = APIRouter()

        @router.put("/items/{item_id}")
        def replace_item(item_id: str, item: Item):
            return {"message": "Item replaced", "id": item_id}

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["PUT"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def post(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP POST operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            description: str | None = None

        app = FastAPI()
        router = APIRouter()

        @router.post("/items/")
        def create_item(item: Item):
            return {"message": "Item created"}

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["POST"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def delete(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP DELETE operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI

        app = FastAPI()
        router = APIRouter()

        @router.delete("/items/{item_id}")
        def delete_item(item_id: str):
            return {"message": "Item deleted"}

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["DELETE"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def options(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP OPTIONS operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI

        app = FastAPI()
        router = APIRouter()

        @router.options("/items/")
        def get_item_options():
            return {"additions": ["Aji", "Guacamole"]}

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["OPTIONS"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def head(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP HEAD operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            description: str | None = None

        app = FastAPI()
        router = APIRouter()

        @router.head("/items/", status_code=204)
        def get_items_headers(response: Response):
            response.headers["X-Cat-Dog"] = "Alone in the world"

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["HEAD"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def patch(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP PATCH operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            description: str | None = None

        app = FastAPI()
        router = APIRouter()

        @router.patch("/items/")
        def update_item(item: Item):
            return {"message": "Item updated in place"}

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["PATCH"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def trace(
        self,
        path: str,
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add a *path operation* using an HTTP TRACE operation.

        Args:
            path: The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.

            response_model: The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).

            status_code: The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

            tags: A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).

            dependencies: A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation
                decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).

            summary: A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            description: A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation
                Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

            response_description: The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            responses: Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            deprecated: Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            operation_id: Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

            response_model_include: Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude: Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_by_alias: Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).

            response_model_exclude_unset: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_defaults: Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).

            response_model_exclude_none: Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return
                Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).

            include_in_schema: Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String
                Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).

            response_class: Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File,
                others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).

            name: Name for this *path operation*. Only used internally.

            callbacks: List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).

            openapi_extra: Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced
                Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).

            generate_unique_id_function: Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate
                Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).

        ## Example

        ```python
        from fastapi import APIRouter, FastAPI
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            description: str | None = None

        app = FastAPI()
        router = APIRouter()

        @router.trace("/items/{item_id}")
        def trace_item(item_id: str):
            return None

        app.include_router(router)
        ```
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=["TRACE"],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    # TODO: remove this once the lifespan (or alternative) interface is improved
    async def _startup(self) -> None:
        """
        Run any `.on_startup` event handlers.

        This method is kept for backward compatibility after Starlette removed
        support for on_startup/on_shutdown handlers.

        Ref: https://github.com/Kludex/starlette/pull/3117
        """
        for handler in self.on_startup:
            if is_async_callable(handler):
                await handler()
            else:
                handler()

    # TODO: remove this once the lifespan (or alternative) interface is improved
    async def _shutdown(self) -> None:
        """
        Run any `.on_shutdown` event handlers.

        This method is kept for backward compatibility after Starlette removed
        support for on_startup/on_shutdown handlers.

        Ref: https://github.com/Kludex/starlette/pull/3117
        """
        for handler in self.on_shutdown:
            if is_async_callable(handler):
                await handler()
            else:
                handler()

    # TODO: remove this once the lifespan (or alternative) interface is improved
    def add_event_handler(
        self,
        event_type: str,
        func: Callable[[], Any],
    ) -> None:
        """
        Add an event handler function for startup or shutdown.

        This method is kept for backward compatibility after Starlette removed
        support for on_startup/on_shutdown handlers.

        Ref: https://github.com/Kludex/starlette/pull/3117
        """
        assert event_type in ("startup", "shutdown")
        if event_type == "startup":
            self.on_startup.append(func)
        else:
            self.on_shutdown.append(func)

    @deprecated(
        """
        on_event is deprecated, use lifespan event handlers instead.

        Read more about it in the
        [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
        """
    )
    def on_event(
        self,
        event_type: str,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Add an event handler for the router.

        `on_event` is deprecated, use `lifespan` event handlers instead.

        Read more about it in the
        [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/#alternative-events-deprecated).

        Args:
            event_type: The type of event. `startup` or `shutdown`.
        """

        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            self.add_event_handler(event_type, func)
            return func

        return decorator
