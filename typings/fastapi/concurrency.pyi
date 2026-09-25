from collections.abc import AsyncGenerator
from contextlib import AbstractContextManager
from contextlib import asynccontextmanager as asynccontextmanager

from starlette.concurrency import iterate_in_threadpool as iterate_in_threadpool  # noqa
from starlette.concurrency import run_in_threadpool as run_in_threadpool  # noqa
from starlette.concurrency import run_until_first_complete as run_until_first_complete  # noqa

__all__ = (
    "asynccontextmanager",
    "contextmanager_in_threadpool",
    "iterate_in_threadpool",
    "run_in_threadpool",
    "run_until_first_complete",
)

@asynccontextmanager
async def contextmanager_in_threadpool[T](cm: AbstractContextManager[T]) -> AsyncGenerator[T]: ...
