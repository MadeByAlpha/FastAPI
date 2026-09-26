import email.message
import functools
import inspect
import json
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, cast

import anyio
from starlette._exception_handler import wrap_app_handling_exceptions
from starlette._utils import is_async_callable
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.websockets import WebSocket

from fastapi import params
from fastapi._compat import Undefined, lenient_issubclass
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.dependencies.models import _is_async_gen_callable, _is_coroutine_callable, _is_gen_callable
from fastapi.dependencies.utils import (
    _get_flat_body_params,
    _should_embed_body_fields,
    get_dependant,
    get_parameterless_sub_dependant,
    solve_dependencies,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import (
    EndpointContext,
    FastAPIError,
    RequestValidationError,
    ResponseValidationError,
    WebSocketRequestValidationError,
)
from fastapi.sse import _PING_INTERVAL, KEEPALIVE_COMMENT, EventSourceResponse, ServerSentEvent, format_sse_event
from fastapi.utils import is_body_allowed_for_status_code

if __debug__ and TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Iterator, Sequence
    from typing import Any

    from anyio.abc import ObjectReceiveStream
    from starlette.datastructures import FormData
    from starlette.types import ASGIApp, Receive, Scope, Send

    from fastapi._compat import ModelField
    from fastapi.dependencies.models import Dependant
    from fastapi.types import IncEx

    __all__ = (
        "_build_dependant_with_parameterless_dependencies",
        "_extract_endpoint_context",
        "get_request_handler",
        "get_websocket_app",
        "request_response",
        "run_endpoint_function",
        "serialize_response",
        "websocket_session",
    )


# Copy of starlette.routing.request_response modified to include the
# dependencies' AsyncExitStack
def request_response(
    func: Callable[[Request], Awaitable[Response] | Response],
) -> ASGIApp:
    """
    Takes a function or coroutine `func(request) -> response`,
    and returns an ASGI application.
    """
    f: Callable[[Request], Awaitable[Response]] = (
        func  # type: ignore[assignment]
        if is_async_callable(func)
        else functools.partial(run_in_threadpool, func)  # type: ignore[call-arg]
    )  # ty: ignore[invalid-assignment]

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive, send)

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            # Starts customization
            response_awaited = False
            async with AsyncExitStack() as request_stack:
                scope["fastapi_inner_astack"] = request_stack
                async with AsyncExitStack() as function_stack:
                    scope["fastapi_function_astack"] = function_stack
                    response = await f(request)
                await response(scope, receive, send)
                # Continues customization
                response_awaited = True
            if not response_awaited:
                raise FastAPIError(
                    "Response not awaited. There's a high chance that the "
                    "application code is raising an exception and a dependency with yield "
                    "has a block with a bare except, or a block with except Exception, "
                    "and is not raising the exception again. Read more about it in the "
                    "docs: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#dependencies-with-yield-and-except"
                )

        # Same as in Starlette
        await wrap_app_handling_exceptions(app, request)(scope, receive, send)

    return app


# Copy of starlette.routing.websocket_session modified to include the
# dependencies' AsyncExitStack
def websocket_session(
    func: Callable[[WebSocket], Awaitable[None]],
) -> ASGIApp:
    """
    Takes a coroutine `func(session)`, and returns an ASGI application.
    """
    # assert asyncio.iscoroutinefunction(func), "WebSocket endpoints must be async"

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        session = WebSocket(scope, receive=receive, send=send)

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            async with AsyncExitStack() as request_stack:
                scope["fastapi_inner_astack"] = request_stack
                async with AsyncExitStack() as function_stack:
                    scope["fastapi_function_astack"] = function_stack
                    await func(session)

        # Same as in Starlette
        await wrap_app_handling_exceptions(app, session)(scope, receive, send)

    return app


# Cache for endpoint context to avoid re-extracting on every request
_endpoint_context_cache: dict[int, EndpointContext] = {}


def _extract_endpoint_context(func: Any) -> EndpointContext:
    """Extract endpoint context with caching to avoid repeated file I/O."""
    func_id = id(func)

    if func_id in _endpoint_context_cache:
        return _endpoint_context_cache[func_id]

    try:
        ctx: EndpointContext = {}

        if (source_file := inspect.getsourcefile(func)) is not None:
            ctx["file"] = source_file
        if (line_number := inspect.getsourcelines(func)[1]) is not None:
            ctx["line"] = line_number
        if (func_name := getattr(func, "__name__", None)) is not None:
            ctx["function"] = func_name
    except Exception:
        ctx = EndpointContext()

    _endpoint_context_cache[func_id] = ctx
    return ctx


async def serialize_response(
    *,
    field: ModelField | None = None,
    response_content: Any,
    include: IncEx | None = None,
    exclude: IncEx | None = None,
    by_alias: bool = True,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
    is_coroutine: bool = True,
    endpoint_ctx: EndpointContext | None = None,
    dump_json: bool = False,
) -> Any:
    if field:
        if is_coroutine:
            value, errors = field.validate(response_content, {}, loc=("response",))
        else:
            value, errors = await run_in_threadpool(field.validate, response_content, {}, loc=("response",))
        if errors:
            ctx = endpoint_ctx or EndpointContext()
            raise ResponseValidationError(
                errors=errors,
                body=response_content,
                endpoint_ctx=ctx,
            )
        serializer = field.serialize_json if dump_json else field.serialize
        return serializer(
            value,
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    else:
        return jsonable_encoder(response_content)


async def run_endpoint_function(*, dependant: Dependant, values: dict[str, Any], is_coroutine: bool) -> Any:
    # Only called by get_request_handler. Has been split into its own function to
    # facilitate profiling endpoints, since inner functions are harder to profile.
    assert dependant.call is not None, "dependant.call must be a function"

    if is_coroutine:
        return await dependant.call(**values)
    else:
        return await run_in_threadpool(dependant.call, **values)


def _build_response_args(*, status_code: int | None, solved_result: Any) -> dict[str, Any]:
    response_args: dict[str, Any] = {
        "background": solved_result.background_tasks,
    }
    # If status_code was set, use it, otherwise use the default from the
    # response class, in the case of redirect it's 307
    current_status_code = status_code if status_code else solved_result.response.status_code
    if current_status_code is not None:
        response_args["status_code"] = current_status_code
    if solved_result.response.status_code:
        response_args["status_code"] = solved_result.response.status_code
    return response_args


def get_request_handler(
    dependant: Dependant,
    body_field: ModelField | None = None,
    status_code: int | None = None,
    response_class: type[Response] | DefaultPlaceholder = Default(JSONResponse),
    response_field: ModelField | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    dependency_overrides_provider: Any | None = None,
    embed_body_fields: bool = False,
    strict_content_type: bool | DefaultPlaceholder = Default(True),
    stream_item_field: ModelField | None = None,
    is_json_stream: bool = False,
) -> Callable[[Request], Coroutine[Any, Any, Response]]:
    assert dependant.call is not None, "dependant.call must be a function"
    is_coroutine = _is_coroutine_callable(dependant.call)
    is_body_form = body_field and isinstance(body_field.field_info, params.Form)
    if isinstance(response_class, DefaultPlaceholder):
        actual_response_class: type[Response] = response_class.value
    else:
        actual_response_class = response_class
    is_sse_stream = lenient_issubclass(actual_response_class, EventSourceResponse)
    if isinstance(strict_content_type, DefaultPlaceholder):
        actual_strict_content_type: bool = strict_content_type.value
    else:
        actual_strict_content_type = strict_content_type

    async def app(request: Request) -> Response:
        response: Response | None = None
        file_stack = request.scope.get("fastapi_middleware_astack")
        assert isinstance(file_stack, AsyncExitStack), "fastapi_middleware_astack not found in request scope"

        # Extract endpoint context for error messages
        endpoint_ctx = _extract_endpoint_context(dependant.call) if dependant.call else EndpointContext()

        if dependant.path:
            # For mounted sub-apps, include the mount path prefix
            mount_path = request.scope.get("root_path", "").rstrip("/")
            endpoint_ctx["path"] = f"{request.method} {mount_path}{dependant.path}"

        # Read body and auto-close files
        try:
            body: Any = None
            if body_field:
                if is_body_form:
                    body = await request.form()
                    file_stack.push_async_callback(body.close)
                else:
                    body_bytes = await request.body()
                    if body_bytes:
                        json_body: Any = Undefined
                        content_type_value = request.headers.get("content-type")
                        if not content_type_value:
                            if not actual_strict_content_type:
                                json_body = await request.json()
                        else:
                            message = email.message.Message()
                            message["content-type"] = content_type_value
                            if message.get_content_maintype() == "application":
                                subtype = message.get_content_subtype()
                                if subtype == "json" or subtype.endswith("+json"):
                                    json_body = await request.json()
                        if json_body != Undefined:
                            body = json_body
                        else:
                            body = body_bytes
        except json.JSONDecodeError as e:
            validation_error = RequestValidationError(
                [
                    {
                        "type": "json_invalid",
                        "loc": ("body", e.pos),
                        "msg": "JSON decode error",
                        "input": {},
                        "ctx": {"error": e.msg},
                    }
                ],
                body=e.doc,
                endpoint_ctx=endpoint_ctx,
            )
            raise validation_error from e
        except HTTPException:
            # If a middleware raises an HTTPException, it should be raised again
            raise
        except Exception as e:
            http_error = HTTPException(status_code=400, detail="There was an error parsing the body")
            raise http_error from e

        # Solve dependencies and run path operation function, auto-closing dependencies
        errors: list[Any] = []
        async_exit_stack = request.scope.get("fastapi_inner_astack")
        assert isinstance(async_exit_stack, AsyncExitStack), "fastapi_inner_astack not found in request scope"
        solved_result = await solve_dependencies(
            request=request,
            dependant=dependant,
            body=cast("dict[str, Any] | FormData | bytes | None", body),
            dependency_overrides_provider=dependency_overrides_provider,
            async_exit_stack=async_exit_stack,
            embed_body_fields=embed_body_fields,
        )
        errors = solved_result.errors
        assert dependant.call  # For types
        if not errors:
            # Shared serializer for stream items (JSONL and SSE).
            # Validates against stream_item_field when set, then
            # serializes to JSON bytes.
            def _serialize_data(data: Any) -> bytes:
                if stream_item_field:
                    value, errors_ = stream_item_field.validate(data, {}, loc=("response",))
                    if errors_:
                        ctx = endpoint_ctx or EndpointContext()
                        raise ResponseValidationError(
                            errors=errors_,
                            body=data,
                            endpoint_ctx=ctx,
                        )
                    return stream_item_field.serialize_json(
                        value,
                        include=response_model_include,
                        exclude=response_model_exclude,
                        by_alias=response_model_by_alias,
                        exclude_unset=response_model_exclude_unset,
                        exclude_defaults=response_model_exclude_defaults,
                        exclude_none=response_model_exclude_none,
                    )
                else:
                    data = jsonable_encoder(data)
                    return json.dumps(data).encode("utf-8")

            if is_sse_stream:
                # Generator endpoint: stream as Server-Sent Events
                gen = dependant.call(**solved_result.values)

                def _serialize_sse_item(item: Any) -> bytes:
                    if isinstance(item, ServerSentEvent):
                        # User controls the event structure.
                        # Serialize the data payload if present.
                        # For ServerSentEvent items we skip stream_item_field
                        # validation (the user may mix types intentionally).
                        if item.raw_data is not None:
                            data_str: str | None = item.raw_data
                        elif item.data is not None:
                            if hasattr(item.data, "model_dump_json"):
                                data_str = item.data.model_dump_json()
                            else:
                                data_str = json.dumps(jsonable_encoder(item.data))
                        else:
                            data_str = None
                        return format_sse_event(
                            data_str=data_str,
                            event=item.event,
                            id=item.id,
                            retry=item.retry,
                            comment=item.comment,
                        )
                    else:
                        # Plain object: validate + serialize via
                        # stream_item_field (if set) and wrap in data field
                        return format_sse_event(data_str=_serialize_data(item).decode("utf-8"))

                if _is_async_gen_callable(dependant.call):
                    sse_aiter: AsyncIterator[Any] = gen.__aiter__()
                else:
                    sse_aiter = iterate_in_threadpool(gen)

                @asynccontextmanager
                async def _sse_producer_cm() -> AsyncIterator[ObjectReceiveStream[bytes]]:
                    # Use a memory stream to decouple generator iteration
                    # from the keepalive timer. A producer task pulls items
                    # from the generator independently, so
                    # `anyio.fail_after` never wraps the generator's
                    # `__anext__` directly - avoiding CancelledError that
                    # would finalize the generator and also working for sync
                    # generators running in a thread pool.
                    #
                    # This context manager is entered on the request-scoped
                    # AsyncExitStack so its __aexit__ (which cancels the
                    # task group) is called by the exit stack after the
                    # streaming response completes — not by async generator
                    # finalization via GeneratorExit.
                    # Ref: https://peps.python.org/pep-0789/
                    send_stream, receive_stream = anyio.create_memory_object_stream[bytes](max_buffer_size=1)

                    async def _producer() -> None:
                        async with send_stream:
                            async for raw_item in sse_aiter:
                                await send_stream.send(_serialize_sse_item(raw_item))

                    send_keepalive, receive_keepalive = anyio.create_memory_object_stream[bytes](max_buffer_size=1)

                    async def _keepalive_inserter() -> None:
                        """Read from the producer and forward to the output,
                        inserting keepalive comments on timeout."""
                        async with send_keepalive, receive_stream:
                            try:
                                while True:
                                    try:
                                        with anyio.fail_after(_PING_INTERVAL):
                                            data = await receive_stream.receive()
                                        await send_keepalive.send(data)
                                    except TimeoutError:
                                        await send_keepalive.send(KEEPALIVE_COMMENT)
                            except anyio.EndOfStream:
                                pass

                    async with anyio.create_task_group() as tg:
                        tg.start_soon(_producer)
                        tg.start_soon(_keepalive_inserter)
                        yield receive_keepalive
                        tg.cancel_scope.cancel()

                # Enter the SSE context manager on the request-scoped
                # exit stack. The stack outlives the streaming response,
                # so __aexit__ runs via proper structured teardown, not
                # via GeneratorExit thrown into an async generator.
                sse_receive_stream = await async_exit_stack.enter_async_context(_sse_producer_cm())
                # Ensure the receive stream is closed when the exit stack
                # unwinds, preventing ResourceWarning from __del__.
                async_exit_stack.push_async_callback(sse_receive_stream.aclose)

                async def _sse_with_checkpoints(
                    stream: ObjectReceiveStream[bytes],
                ) -> AsyncIterator[bytes]:
                    async for data in stream:
                        yield data
                        # Guarantee a checkpoint so cancellation can be
                        # delivered even when the producer is faster than
                        # the consumer and receive() never suspends.
                        await anyio.sleep(0)

                sse_stream_content: AsyncIterator[bytes] | Iterator[bytes] = _sse_with_checkpoints(sse_receive_stream)

                response_args = _build_response_args(status_code=status_code, solved_result=solved_result)
                response = StreamingResponse(
                    sse_stream_content,
                    media_type="text/event-stream",
                    **response_args,
                )
                response.headers["Cache-Control"] = "no-cache"
                # For Nginx proxies to not buffer server sent events
                response.headers["X-Accel-Buffering"] = "no"
                response.headers.raw.extend(solved_result.response.headers.raw)
            elif is_json_stream:
                # Generator endpoint: stream as JSONL
                gen = dependant.call(**solved_result.values)

                def _serialize_item(item: Any) -> bytes:
                    return _serialize_data(item) + b"\n"

                if _is_async_gen_callable(dependant.call):

                    async def _async_stream_jsonl() -> AsyncIterator[bytes]:
                        async for item in gen:
                            yield _serialize_item(item)
                            # To allow for cancellation to trigger
                            # Ref: https://github.com/fastapi/fastapi/issues/14680
                            await anyio.sleep(0)

                    jsonl_stream_content: AsyncIterator[bytes] | Iterator[bytes] = _async_stream_jsonl()
                else:

                    def _sync_stream_jsonl() -> Iterator[bytes]:
                        for item in gen:  # ty: ignore[not-iterable]
                            yield _serialize_item(item)

                    jsonl_stream_content = _sync_stream_jsonl()

                response_args = _build_response_args(status_code=status_code, solved_result=solved_result)
                response = StreamingResponse(
                    jsonl_stream_content,
                    media_type="application/jsonl",
                    **response_args,
                )
                response.headers.raw.extend(solved_result.response.headers.raw)
            elif _is_async_gen_callable(dependant.call) or _is_gen_callable(dependant.call):
                # Raw streaming with explicit response_class (e.g. StreamingResponse)
                gen = dependant.call(**solved_result.values)
                if _is_async_gen_callable(dependant.call):

                    async def _async_stream_raw(
                        async_gen: AsyncIterator[Any],
                    ) -> AsyncIterator[Any]:
                        async for chunk in async_gen:
                            yield chunk
                            # To allow for cancellation to trigger
                            # Ref: https://github.com/fastapi/fastapi/issues/14680
                            await anyio.sleep(0)

                    gen = _async_stream_raw(gen)
                response_args = _build_response_args(status_code=status_code, solved_result=solved_result)
                response = actual_response_class(content=gen, **response_args)
                response.headers.raw.extend(solved_result.response.headers.raw)
            else:
                raw_response = await run_endpoint_function(
                    dependant=dependant,
                    values=solved_result.values,
                    is_coroutine=is_coroutine,
                )
                if isinstance(raw_response, Response):
                    if raw_response.background is None:
                        raw_response.background = solved_result.background_tasks
                    response = raw_response
                else:
                    response_args = _build_response_args(status_code=status_code, solved_result=solved_result)
                    # Use the fast path (dump_json) when no custom response
                    # class was set and a response field with a TypeAdapter
                    # exists. Serializes directly to JSON bytes via Pydantic's
                    # Rust core, skipping the intermediate Python dict +
                    # json.dumps() step.
                    use_dump_json = response_field is not None and isinstance(response_class, DefaultPlaceholder)
                    content = await serialize_response(
                        field=response_field,
                        response_content=raw_response,
                        include=response_model_include,
                        exclude=response_model_exclude,
                        by_alias=response_model_by_alias,
                        exclude_unset=response_model_exclude_unset,
                        exclude_defaults=response_model_exclude_defaults,
                        exclude_none=response_model_exclude_none,
                        is_coroutine=is_coroutine,
                        endpoint_ctx=endpoint_ctx,
                        dump_json=use_dump_json,
                    )
                    if use_dump_json:
                        response = Response(
                            content=content,
                            media_type="application/json",
                            **response_args,
                        )
                    else:
                        response = actual_response_class(content, **response_args)
                    if not is_body_allowed_for_status_code(response.status_code):
                        response.body = b""
                    response.headers.raw.extend(solved_result.response.headers.raw)
        if errors:
            validation_error = RequestValidationError(errors, body=body, endpoint_ctx=endpoint_ctx)
            raise validation_error

        # Return response
        assert response
        return response

    return app


def get_websocket_app(
    dependant: Dependant,
    dependency_overrides_provider: Any | None = None,
    embed_body_fields: bool = False,
) -> Callable[[WebSocket], Coroutine[Any, Any, Any]]:
    async def app(websocket: WebSocket) -> None:
        endpoint_ctx = _extract_endpoint_context(dependant.call) if dependant.call else EndpointContext()
        if dependant.path:
            # For mounted sub-apps, include the mount path prefix
            mount_path = websocket.scope.get("root_path", "").rstrip("/")
            endpoint_ctx["path"] = f"WS {mount_path}{dependant.path}"
        async_exit_stack = websocket.scope.get("fastapi_inner_astack")
        assert isinstance(async_exit_stack, AsyncExitStack), "fastapi_inner_astack not found in request scope"
        solved_result = await solve_dependencies(
            request=websocket,
            dependant=dependant,
            dependency_overrides_provider=dependency_overrides_provider,
            async_exit_stack=async_exit_stack,
            embed_body_fields=embed_body_fields,
        )
        if solved_result.errors:
            raise WebSocketRequestValidationError(
                solved_result.errors,
                endpoint_ctx=endpoint_ctx,
            )
        assert dependant.call is not None, "dependant.call must be a function"
        await dependant.call(**solved_result.values)

    return app


def _build_dependant_with_parameterless_dependencies(
    *,
    path: str,
    call: Callable[..., Any],
    dependencies: Sequence[params.Depends],
) -> tuple[Dependant, list[ModelField], bool]:
    dependant = get_dependant(path=path, call=call, scope="function")
    for depends in dependencies[::-1]:
        dependant.dependencies.insert(
            0,
            get_parameterless_sub_dependant(depends=depends, path=path),
        )
    body_params = _get_flat_body_params(dependant)
    embed_body_fields = _should_embed_body_fields(body_params)
    return dependant, body_params, embed_body_fields
