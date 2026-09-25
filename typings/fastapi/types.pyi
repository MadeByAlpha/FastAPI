from collections.abc import Callable
from enum import Enum
from types import UnionType as UnionType
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic.main import IncEx as IncEx

DecoratedCallable = TypeVar("DecoratedCallable", bound=Callable[..., Any])
type ModelNameMap = dict[type[BaseModel | Enum], str]
type DependencyCacheKey = tuple[Callable[..., Any] | None, tuple[str, ...], str]

__all__ = (
    "DecoratedCallable",
    "DependencyCacheKey",
    "IncEx",
    "ModelNameMap",
    "UnionType",
)
