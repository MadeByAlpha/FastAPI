# `fastapi` must be initialized before any `alpha93.fastapi` module, since `fastapi.routing` re-exports from here.
import fastapi  # noqa: F401
