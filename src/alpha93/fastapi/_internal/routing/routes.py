import inspect
from enum import IntEnum
from typing import TYPE_CHECKING, cast

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Match, Route, WebSocketRoute, compile_path, get_name

from fastapi._compat import lenient_issubclass
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.dependencies.models import _is_async_gen_callable, _is_gen_callable
from fastapi.dependencies.utils import _get_body_field, get_stream_item_type, get_typed_return_annotation
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.utils import create_model_field, generate_unique_id, is_body_allowed_for_status_code

from ._handlers import (
    _build_dependant_with_parameterless_dependencies,
    get_request_handler,
    get_websocket_app,
    request_response,
    websocket_session,
)
from ._scope import _effective_route_context_var, _get_scope_effective_route_context

if __debug__ and TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Sequence
    from enum import Enum
    from typing import Any, Protocol

    from starlette.requests import Request
    from starlette.routing import BaseRoute
    from starlette.types import Receive, Scope, Send

    from fastapi import params
    from fastapi._compat import ModelField
    from fastapi.dependencies.models import Dependant
    from fastapi.types import IncEx

    class _APIRouteLike(Protocol):
        path: str
        endpoint: Callable[..., Any]
        stream_item_type: Any | None
        response_model: Any
        summary: str | None
        response_description: str
        deprecated: bool | None
        operation_id: str | None
        response_model_include: IncEx | None
        response_model_exclude: IncEx | None
        response_model_by_alias: bool
        response_model_exclude_unset: bool
        response_model_exclude_defaults: bool
        response_model_exclude_none: bool
        include_in_schema: bool
        response_class: type[Response] | DefaultPlaceholder
        dependency_overrides_provider: Any | None
        callbacks: list[BaseRoute] | None
        openapi_extra: dict[str, Any] | None
        generate_unique_id_function: Callable[[Any], str] | DefaultPlaceholder
        strict_content_type: bool | DefaultPlaceholder
        tags: list[str | Enum]
        responses: dict[int | str, dict[str, Any]]
        name: str
        path_regex: Any
        path_format: str
        param_convertors: dict[str, Any]
        methods: set[str]
        unique_id: str
        status_code: int | None
        response_field: ModelField | None
        stream_item_field: ModelField | None
        dependencies: list[params.Depends]
        description: str
        response_fields: dict[int | str, ModelField]
        dependant: Dependant
        _embed_body_fields: bool
        body_field: ModelField | None
        is_sse_stream: bool
        is_json_stream: bool

    __all__ = (
        "APIRoute",
        "APIWebSocketRoute",
        "_APIRouteLike",
        "_populate_api_route_state",
    )


class APIWebSocketRoute(WebSocketRoute):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        name: str | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        dependency_overrides_provider: Any | None = None,
    ) -> None:
        self.path = path
        self.endpoint = endpoint
        self.name = get_name(endpoint) if name is None else name
        self.dependencies = list(dependencies or [])
        self.path_regex, self.path_format, self.param_convertors = compile_path(path)
        (
            self.dependant,
            _,
            self._embed_body_fields,
        ) = _build_dependant_with_parameterless_dependencies(
            path=self.path_format,
            call=self.endpoint,
            dependencies=self.dependencies,
        )
        self.app = websocket_session(
            get_websocket_app(
                dependant=self.dependant,
                dependency_overrides_provider=dependency_overrides_provider,
                embed_body_fields=self._embed_body_fields,
            )
        )

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope = super().matches(scope)
        if match != Match.NONE:
            child_scope["route"] = self
        return match, child_scope


def _populate_api_route_state(
    route: _APIRouteLike,
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
    name: str | None = None,
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
    dependency_overrides_provider: Any | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[Any], str] | DefaultPlaceholder = Default(generate_unique_id),
    strict_content_type: bool | DefaultPlaceholder = Default(True),
    stream_item_type: Any | None = None,
) -> None:
    route.path = path
    route.endpoint = endpoint
    route.stream_item_type = stream_item_type
    route.summary = summary
    route.response_description = response_description
    route.deprecated = deprecated
    route.operation_id = operation_id
    route.response_model_include = response_model_include
    route.response_model_exclude = response_model_exclude
    route.response_model_by_alias = response_model_by_alias
    route.response_model_exclude_unset = response_model_exclude_unset
    route.response_model_exclude_defaults = response_model_exclude_defaults
    route.response_model_exclude_none = response_model_exclude_none
    route.include_in_schema = include_in_schema
    route.response_class = response_class
    route.dependency_overrides_provider = dependency_overrides_provider
    route.callbacks = callbacks
    route.openapi_extra = openapi_extra
    route.generate_unique_id_function = generate_unique_id_function
    route.strict_content_type = strict_content_type
    route.tags = tags or []
    route.responses = responses or {}
    route.name = get_name(endpoint) if name is None else name
    route.path_regex, route.path_format, route.param_convertors = compile_path(path)
    if methods is None:
        methods = ["GET"]
    route.methods = {method.upper() for method in methods}
    if isinstance(generate_unique_id_function, DefaultPlaceholder):
        current_generate_unique_id: Callable[[Any], str] = generate_unique_id_function.value
    else:
        current_generate_unique_id = generate_unique_id_function
    route.unique_id = route.operation_id or current_generate_unique_id(route)
    # normalize enums e.g. http.HTTPStatus
    if isinstance(status_code, IntEnum):
        status_code = int(status_code)
    route.status_code = status_code
    route.dependencies = list(dependencies or [])
    route.description = description or inspect.cleandoc(route.endpoint.__doc__ or "")
    # if a "form feed" character (page break) is found in the description text,
    # truncate description text to the content preceding the first "form feed"
    route.description = route.description.split("\f")[0].strip()
    response_fields = {}
    for additional_status_code, response in route.responses.items():
        assert isinstance(response, dict), "An additional response must be a dict"
        model = response.get("model")
        if model:
            assert is_body_allowed_for_status_code(additional_status_code), (
                f"Status code {additional_status_code} must not have a response body"
            )
            response_name = f"Response_{additional_status_code}_{route.unique_id}"
            response_field = create_model_field(name=response_name, type_=model, mode="serialization")
            response_fields[additional_status_code] = response_field
    if response_fields:
        route.response_fields = response_fields
    else:
        route.response_fields = {}

    assert callable(endpoint), "An endpoint must be a callable"
    (
        route.dependant,
        body_params,
        route._embed_body_fields,
    ) = _build_dependant_with_parameterless_dependencies(
        path=route.path_format,
        call=route.endpoint,
        dependencies=route.dependencies,
    )
    route.body_field = _get_body_field(
        body_params=body_params,
        name=route.unique_id,
        embed_body_fields=route._embed_body_fields,
    )
    # Detect generator endpoints that should stream as JSONL or SSE
    is_generator = _is_async_gen_callable(route.dependant.call) or _is_gen_callable(route.dependant.call)
    route.is_sse_stream = is_generator and lenient_issubclass(response_class, EventSourceResponse)
    route.is_json_stream = is_generator and isinstance(response_class, DefaultPlaceholder)
    if isinstance(response_model, DefaultPlaceholder):
        return_annotation = get_typed_return_annotation(endpoint)
        if lenient_issubclass(return_annotation, Response):
            response_model = None
        else:
            stream_item = get_stream_item_type(return_annotation)
            if stream_item is not None and is_generator:
                # Extract item type for JSONL or SSE streaming for
                # generator endpoints when response_class is
                # DefaultPlaceholder (JSONL) or EventSourceResponse (SSE).
                # ServerSentEvent is excluded: it's a transport
                # wrapper, not a data model, so it shouldn't feed
                # into validation or OpenAPI schema generation.
                if (
                    isinstance(response_class, DefaultPlaceholder)
                    or lenient_issubclass(response_class, EventSourceResponse)
                ) and not lenient_issubclass(stream_item, ServerSentEvent):
                    route.stream_item_type = stream_item
                response_model = None
            else:
                response_model = return_annotation
    route.response_model = response_model
    if route.response_model:
        assert is_body_allowed_for_status_code(status_code), f"Status code {status_code} must not have a response body"
        response_name = "Response_" + route.unique_id
        route.response_field = create_model_field(
            name=response_name,
            type_=route.response_model,
            mode="serialization",
        )
    else:
        route.response_field = None
    if route.stream_item_type:
        stream_item_name = "StreamItem_" + route.unique_id
        route.stream_item_field = create_model_field(
            name=stream_item_name,
            type_=route.stream_item_type,
            mode="serialization",
        )
    else:
        route.stream_item_field = None


class APIRoute(Route):
    stream_item_type: Any | None
    response_model: Any
    summary: str | None
    response_description: str
    deprecated: bool | None
    operation_id: str | None
    response_model_include: IncEx | None
    response_model_exclude: IncEx | None
    response_model_by_alias: bool
    response_model_exclude_unset: bool
    response_model_exclude_defaults: bool
    response_model_exclude_none: bool
    include_in_schema: bool
    response_class: type[Response] | DefaultPlaceholder
    dependency_overrides_provider: Any | None
    callbacks: list[BaseRoute] | None
    openapi_extra: dict[str, Any] | None
    generate_unique_id_function: Callable[[Any], str] | DefaultPlaceholder
    strict_content_type: bool | DefaultPlaceholder
    tags: list[str | Enum]
    responses: dict[int | str, dict[str, Any]]
    unique_id: str
    status_code: int | None
    response_field: ModelField | None
    stream_item_field: ModelField | None
    dependencies: list[params.Depends]
    description: str
    response_fields: dict[int | str, ModelField]
    dependant: Dependant
    _embed_body_fields: bool
    body_field: ModelField | None
    is_sse_stream: bool
    is_json_stream: bool

    def __init__(
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
        name: str | None = None,
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
        dependency_overrides_provider: Any | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[["APIRoute"], str] | DefaultPlaceholder = Default(generate_unique_id),
        strict_content_type: bool | DefaultPlaceholder = Default(True),
    ) -> None:
        _populate_api_route_state(
            cast("_APIRouteLike", self),
            path,
            endpoint,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            name=name,
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
            dependency_overrides_provider=dependency_overrides_provider,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
            strict_content_type=strict_content_type,
        )
        self.app = request_response(self.get_route_handler())

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        route = cast("_APIRouteLike", self)
        # TODO: Replace or deprecate this no-scope hook so included-route
        # effective context can be passed explicitly instead of via ContextVar.
        effective_context = _effective_route_context_var.get()
        if effective_context is not None and effective_context.original_route is self:
            route = cast("_APIRouteLike", effective_context)
        return get_request_handler(
            dependant=route.dependant,
            body_field=route.body_field,
            status_code=route.status_code,
            response_class=route.response_class,
            response_field=route.response_field,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
            response_model_exclude_unset=route.response_model_exclude_unset,
            response_model_exclude_defaults=route.response_model_exclude_defaults,
            response_model_exclude_none=route.response_model_exclude_none,
            dependency_overrides_provider=route.dependency_overrides_provider,
            embed_body_fields=route._embed_body_fields,
            strict_content_type=route.strict_content_type,
            stream_item_field=route.stream_item_field,
            is_json_stream=route.is_json_stream,
        )

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        effective_context = _get_scope_effective_route_context(scope)
        if effective_context is not None and effective_context.original_route is self:
            match, child_scope = effective_context.matches(scope)
        else:
            match, child_scope = super().matches(scope)
        if match != Match.NONE:
            child_scope["route"] = self
        return match, child_scope

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        effective_context = _get_scope_effective_route_context(scope)
        if effective_context is not None and effective_context.original_route is self:
            methods = effective_context.methods
            if methods and scope["method"] not in methods:
                headers = {"Allow": ", ".join(methods)}
                if "app" in scope:
                    raise HTTPException(status_code=405, headers=headers)
                response = PlainTextResponse("Method Not Allowed", status_code=405, headers=headers)
                await response(scope, receive, send)
                return
            token = _effective_route_context_var.set(effective_context)
            try:
                app = request_response(self.get_route_handler())
            finally:
                _effective_route_context_var.reset(token)
            await app(scope, receive, send)
            return
        await super().handle(scope, receive, send)
