from collections.abc import Callable, Mapping
from typing import Any, BinaryIO, Final

from pydantic import GetJsonSchemaHandler
from starlette.datastructures import URL as URL  # noqa: F401
from starlette.datastructures import Address as Address  # noqa: F401
from starlette.datastructures import FormData as FormData  # noqa: F401
from starlette.datastructures import Headers as Headers  # noqa: F401
from starlette.datastructures import QueryParams as QueryParams  # noqa: F401
from starlette.datastructures import State as State  # noqa: F401
from starlette.datastructures import UploadFile as StarletteUploadFile

__all__ = (
    "URL",
    "Address",
    "Default",
    "DefaultPlaceholder",
    "DefaultType",
    "FormData",
    "Headers",
    "QueryParams",
    "State",
    "UploadFile",
    "_Unset",
)

class UploadFile(StarletteUploadFile):
    """
    A file uploaded in a request.

    Define it as a *path operation function* (or dependency) parameter.

    If you are using a regular `def` function, you can use the `upload_file.file`
    attribute to access the raw standard Python file (blocking, not async), useful and
    needed for non-async code.

    Read more about it in the
    [FastAPI docs for Request Files](https://fastapi.tiangolo.com/tutorial/request-files/).

    ## Example

    ```python
    from typing import Annotated

    from fastapi import FastAPI, File, UploadFile

    app = FastAPI()


    @app.post("/files/")
    async def create_file(file: Annotated[bytes, File()]):
        return {"file_size": len(file)}


    @app.post("/uploadfile/")
    async def create_upload_file(file: UploadFile):
        return {"filename": file.filename}
    ```
    """

    file: BinaryIO
    """
    The standard Python file object (non-async).
    """
    filename: str | None
    """
    The original file name.
    """
    size: int | None
    """
    The size of the file in bytes.
    """
    headers: Headers
    """
    The headers of the request.
    """
    content_type: str | None
    """
    The content type of the request, from the headers.
    """
    async def write(self, data: bytes) -> None:
        """
        Write some bytes to the file.

        You normally wouldn't use this from a file you read in a request.

        To be awaitable, compatible with async, this is run in threadpool.

        Args:
            data: The bytes to write to the file.
        """

    async def read(self, size: int = ...) -> bytes:
        """
        Read some bytes from the file.

        To be awaitable, compatible with async, this is run in threadpool.

        Args:
            size: The number of bytes to read from the file.
        """

    async def seek(self, offset: int) -> None:
        """
        Move to a position in the file.

        Any next read or write will be done from that position.

        To be awaitable, compatible with async, this is run in threadpool.

        Args:
            offset: The position in bytes to seek to in the file.
        """

    async def close(self) -> None:
        """
        Close the file.

        To be awaitable, compatible with async, this is run in threadpool.
        """

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: Mapping[str, Any], handler: GetJsonSchemaHandler
    ) -> dict[str, Any]: ...
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: Callable[[Any], Mapping[str, Any]]
    ) -> Mapping[str, Any]: ...

class DefaultPlaceholder[T]:
    """
    You shouldn't use this class directly.

    It's used internally to recognize when a default value has been overwritten, even
    if the overridden default value was truthy.
    """
    __slots__ = ("value",)

    value: Final[T | None]

    def __init__(self, value: Any) -> None: ...
    def __bool__(self) -> bool: ...
    def __eq__(self, o: object) -> bool: ...

type DefaultType[T] = T

def Default[T](value: T) -> T:
    """
    You shouldn't use this function directly.

    It's used internally to recognize when a default value has been overwritten, even
    if the overridden default value was truthy.
    """

_Unset: Final[DefaultType] = ...
