from collections.abc import Callable, Sequence
from typing import Annotated, Any, Literal
from warnings import deprecated

from fastapi.openapi.models import Example
from pydantic import AliasChoices, AliasPath

def Path(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | None = ...,
    alias: str | None = ...,
    alias_priority: int | None = ...,
    validation_alias: str | AliasPath | AliasChoices | None = ...,
    serialization_alias: str | None = ...,
    title: str | None = ...,
    description: str | None = ...,
    gt: float | None = ...,
    ge: float | None = ...,
    lt: float | None = ...,
    le: float | None = ...,
    min_length: int | None = ...,
    max_length: int | None = ...,
    pattern: str | None = ...,
    regex: Annotated[
        str | None,
        deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
    ] = ...,
    discriminator: str | None = ...,
    strict: bool | None = ...,
    multiple_of: float | None = ...,
    allow_inf_nan: bool | None = ...,
    max_digits: int | None = ...,
    decimal_places: int | None = ...,
    examples: list[Any] | None = ...,
    example: Annotated[
        Any | None,
        deprecated(
            "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
            "although still supported. Use examples instead."
        ),
    ] = ...,
    openapi_examples: dict[str, Example] | None = ...,
    deprecated: deprecated | str | bool | None = ...,
    include_in_schema: bool = ...,
    json_schema_extra: dict[str, Any] | None = ...,
    **extra: Annotated[
        Any,
        deprecated("""
            The `extra` kwargs is deprecated. Use `json_schema_extra` instead.
            """),
    ],
) -> Any:
    """
    Declare a path parameter for a *path operation*.

    Read more about it in the
    [FastAPI docs for Path Parameters and Numeric Validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/).

    ```python
    from typing import Annotated

    from fastapi import FastAPI, Path

    app = FastAPI()


    @app.get("/items/{item_id}")
    async def read_items(
        item_id: Annotated[int, Path(title="The ID of the item to get")],
    ):
        return {"item_id": item_id}
    ```

    Args:
        default: Default value if the parameter field is not set.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        default_factory: A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        alias: An alternative name for the parameter field.

            This will be used to extract the data and for the generated OpenAPI.
            It is particularly useful when you can't use the name you want because it
            is a Python reserved keyword or similar.

        alias_priority: Priority of the alias. This affects whether an alias generator is used.

        validation_alias: 'Whitelist' validation step. The parameter field will be the single one
            allowed by the alias or set of aliases defined.

        serialization_alias: 'Blacklist' validation step. The vanilla parameter field will be the
            single one of the alias' or set of aliases' fields and all the other
            fields will be ignored at serialization time.

        title: Human-readable title.

            Read more about it in the
            [FastAPI docs for Path Parameters and Numeric
            Validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#declare-metadata)

        description: Human-readable description.

        gt: Greater than. If set, value must be greater than this. Only applicable to
            numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        ge: Greater than or equal. If set, value must be greater than or equal to
            this. Only applicable to numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        lt: Less than. If set, value must be less than this. Only applicable to numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        le: Less than or equal. If set, value must be less than or equal to this.
            Only applicable to numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        min_length: Minimum length for strings.

        max_length: Maximum length for strings.

        pattern: RegEx pattern for strings.

        regex: RegEx pattern for strings.

        discriminator: Parameter field name for discriminating the type in a tagged union.

        strict: If `True`, strict validation is applied to the field.

        multiple_of: Value must be a multiple of this. Only applicable to numbers.

        allow_inf_nan: Allow `inf`, `-inf`, `nan`. Only applicable to numbers.

        max_digits: Maximum number of digits allowed for decimal values.

        decimal_places: Maximum number of decimal places allowed for decimal values.

        examples: Example values for this field.

            Read more about it in the
            [FastAPI docs for Declare Request Example Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/)

        openapi_examples: OpenAPI-specific examples.

            It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            Swagger UI (that provides the `/docs` interface) has better support for the
            OpenAPI-specific examples than the JSON Schema `examples`, that's the main
            use case for this.

            Read more about it in the
            [FastAPI docs for Declare Request Example
            Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/#using-the-openapi_examples-parameter).

        deprecated: Mark this parameter field as deprecated.

            It will affect the generated OpenAPI (e.g. visible at `/docs`).

        include_in_schema: To include (or not) this parameter field in the generated OpenAPI.
            You probably don't need it, but it's available.

            This affects the generated OpenAPI (e.g. visible at `/docs`).

        json_schema_extra: Any additional JSON schema data.

        **extra: Include extra fields used by the JSON Schema.
    """

def Query(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | None = ...,
    alias: str | None = ...,
    alias_priority: int | None = ...,
    validation_alias: str | AliasPath | AliasChoices | None = ...,
    serialization_alias: str | None = ...,
    title: str | None = ...,
    description: str | None = ...,
    gt: float | None = ...,
    ge: float | None = ...,
    lt: float | None = ...,
    le: float | None = ...,
    min_length: int | None = ...,
    max_length: int | None = ...,
    pattern: str | None = ...,
    regex: Annotated[
        str | None,
        deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
    ] = ...,
    discriminator: str | None = ...,
    strict: bool | None = ...,
    multiple_of: float | None = ...,
    allow_inf_nan: bool | None = ...,
    max_digits: int | None = ...,
    decimal_places: int | None = ...,
    examples: list[Any] | None = ...,
    example: Annotated[
        Any | None,
        deprecated(
            "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
            "although still supported. Use examples instead."
        ),
    ] = ...,
    openapi_examples: dict[str, Example] | None = ...,
    deprecated: deprecated | str | bool | None = ...,
    include_in_schema: bool = ...,
    json_schema_extra: dict[str, Any] | None = ...,
    **extra: Annotated[
        Any,
        deprecated("""
            The `extra` kwargs is deprecated. Use `json_schema_extra` instead.
            """),
    ],
) -> Any:
    """
    Args:
        default: Default value if the parameter field is not set.

            Read more about it in the
            [FastAPI docs about Query
            parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#alternative-old-query-as-the-default-value)

        default_factory: A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        alias: An alternative name for the parameter field.

            This will be used to extract the data and for the generated OpenAPI.
            It is particularly useful when you can't use the name you want because it
            is a Python reserved keyword or similar.

            Read more about it in the
            [FastAPI docs about Query
            parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#alias-parameters)

        alias_priority: Priority of the alias. This affects whether an alias generator is used.

        validation_alias: 'Whitelist' validation step. The parameter field will be the single one
            allowed by the alias or set of aliases defined.

        serialization_alias: 'Blacklist' validation step. The vanilla parameter field will be the
            single one of the alias' or set of aliases' fields and all the other
            fields will be ignored at serialization time.

        title: Human-readable title.

            Read more about it in the
            [FastAPI docs about Query
            parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#declare-more-metadata)

        description: Human-readable description.

            Read more about it in the
            [FastAPI docs about Query
            parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#declare-more-metadata)

        gt: Greater than. If set, value must be greater than this. Only applicable to
            numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        ge: Greater than or equal. If set, value must be greater than or equal to
            this. Only applicable to numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        lt: Less than. If set, value must be less than this. Only applicable to numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        le: Less than or equal. If set, value must be less than or equal to this.
            Only applicable to numbers.

            Read more about it in the
            [FastAPI docs about Path parameters numeric
            validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/#number-validations-greater-than-and-less-than-or-equal)

        min_length: Minimum length for strings.

            Read more about it in the
            [FastAPI docs about Query parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/)

        max_length: Maximum length for strings.

            Read more about it in the
            [FastAPI docs about Query parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/)

        pattern: RegEx pattern for strings.

            Read more about it in the
            [FastAPI docs about Query
            parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#add-regular-expressions

        regex: RegEx pattern for strings.

        discriminator: Parameter field name for discriminating the type in a tagged union.

        strict: If `True`, strict validation is applied to the field.

        multiple_of: Value must be a multiple of this. Only applicable to numbers.

        allow_inf_nan: Allow `inf`, `-inf`, `nan`. Only applicable to numbers.

        max_digits: Maximum number of digits allowed for decimal values.

        decimal_places: Maximum number of decimal places allowed for decimal values.

        examples: Example values for this field.

            Read more about it in the
            [FastAPI docs for Declare Request Example Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/)

        openapi_examples: OpenAPI-specific examples.

            It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            Swagger UI (that provides the `/docs` interface) has better support for the
            OpenAPI-specific examples than the JSON Schema `examples`, that's the main
            use case for this.

            Read more about it in the
            [FastAPI docs for Declare Request Example
            Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/#using-the-openapi_examples-parameter).

        deprecated: Mark this parameter field as deprecated.

            It will affect the generated OpenAPI (e.g. visible at `/docs`).

            Read more about it in the
            [FastAPI docs about Query
            parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#deprecating-parameters)

        include_in_schema: To include (or not) this parameter field in the generated OpenAPI.
            You probably don't need it, but it's available.

            This affects the generated OpenAPI (e.g. visible at `/docs`).

            Read more about it in the
            [FastAPI docs about Query
            parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi

        json_schema_extra: Any additional JSON schema data.

        **extra: Include extra fields used by the JSON Schema.
    """

def Header(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | None = ...,
    alias: str | None = ...,
    alias_priority: int | None = ...,
    validation_alias: str | AliasPath | AliasChoices | None = ...,
    serialization_alias: str | None = ...,
    convert_underscores: bool = ...,
    title: str | None = ...,
    description: str | None = ...,
    gt: float | None = ...,
    ge: float | None = ...,
    lt: float | None = ...,
    le: float | None = ...,
    min_length: int | None = ...,
    max_length: int | None = ...,
    pattern: str | None = ...,
    regex: Annotated[
        str | None,
        deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
    ] = ...,
    discriminator: str | None = ...,
    strict: bool | None = ...,
    multiple_of: float | None = ...,
    allow_inf_nan: bool | None = ...,
    max_digits: int | None = ...,
    decimal_places: int | None = ...,
    examples: list[Any] | None = ...,
    example: Annotated[
        Any | None,
        deprecated(
            "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
            "although still supported. Use examples instead."
        ),
    ] = ...,
    openapi_examples: dict[str, Example] | None = ...,
    deprecated: deprecated | str | bool | None = ...,
    include_in_schema: bool = ...,
    json_schema_extra: dict[str, Any] | None = ...,
    **extra: Annotated[
        Any,
        deprecated("""
            The `extra` kwargs is deprecated. Use `json_schema_extra` instead.
            """),
    ],
) -> Any:
    """
    Args:
        default: Default value if the parameter field is not set.

        default_factory: A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        alias: An alternative name for the parameter field.

            This will be used to extract the data and for the generated OpenAPI.
            It is particularly useful when you can't use the name you want because it
            is a Python reserved keyword or similar.

        alias_priority: Priority of the alias. This affects whether an alias generator is used.

        validation_alias: 'Whitelist' validation step. The parameter field will be the single one
            allowed by the alias or set of aliases defined.

        serialization_alias: 'Blacklist' validation step. The vanilla parameter field will be the
            single one of the alias' or set of aliases' fields and all the other
            fields will be ignored at serialization time.

        convert_underscores: Automatically convert underscores to hyphens in the parameter field name.

            Read more about it in the
            [FastAPI docs for Header
            Parameters](https://fastapi.tiangolo.com/tutorial/header-params/#automatic-conversion)

        title: Human-readable title.

        description: Human-readable description.

        gt: Greater than. If set, value must be greater than this. Only applicable to
            numbers.

        ge: Greater than or equal. If set, value must be greater than or equal to
            this. Only applicable to numbers.

        lt: Less than. If set, value must be less than this. Only applicable to numbers.

        le: Less than or equal. If set, value must be less than or equal to this.
            Only applicable to numbers.

        min_length: Minimum length for strings.

        max_length: Maximum length for strings.

        pattern: RegEx pattern for strings.

        regex: RegEx pattern for strings.

        discriminator: Parameter field name for discriminating the type in a tagged union.

        strict: If `True`, strict validation is applied to the field.

        multiple_of: Value must be a multiple of this. Only applicable to numbers.

        allow_inf_nan: Allow `inf`, `-inf`, `nan`. Only applicable to numbers.

        max_digits: Maximum number of digits allowed for decimal values.

        decimal_places: Maximum number of decimal places allowed for decimal values.

        examples: Example values for this field.

            Read more about it in the
            [FastAPI docs for Declare Request Example Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/)

        openapi_examples: OpenAPI-specific examples.

            It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            Swagger UI (that provides the `/docs` interface) has better support for the
            OpenAPI-specific examples than the JSON Schema `examples`, that's the main
            use case for this.

            Read more about it in the
            [FastAPI docs for Declare Request Example
            Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/#using-the-openapi_examples-parameter).

        deprecated: Mark this parameter field as deprecated.

            It will affect the generated OpenAPI (e.g. visible at `/docs`).

        include_in_schema: To include (or not) this parameter field in the generated OpenAPI.
            You probably don't need it, but it's available.

            This affects the generated OpenAPI (e.g. visible at `/docs`).

        json_schema_extra: Any additional JSON schema data.

        **extra: Include extra fields used by the JSON Schema.
    """

def Cookie(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | None = ...,
    alias: str | None = ...,
    alias_priority: int | None = ...,
    validation_alias: str | AliasPath | AliasChoices | None = ...,
    serialization_alias: str | None = ...,
    title: str | None = ...,
    description: str | None = ...,
    gt: float | None = ...,
    ge: float | None = ...,
    lt: float | None = ...,
    le: float | None = ...,
    min_length: int | None = ...,
    max_length: int | None = ...,
    pattern: str | None = ...,
    regex: Annotated[
        str | None,
        deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
    ] = ...,
    discriminator: str | None = ...,
    strict: bool | None = ...,
    multiple_of: float | None = ...,
    allow_inf_nan: bool | None = ...,
    max_digits: int | None = ...,
    decimal_places: int | None = ...,
    examples: list[Any] | None = ...,
    example: Annotated[
        Any | None,
        deprecated(
            "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
            "although still supported. Use examples instead."
        ),
    ] = ...,
    openapi_examples: dict[str, Example] | None = ...,
    deprecated: deprecated | str | bool | None = ...,
    include_in_schema: bool = ...,
    json_schema_extra: dict[str, Any] | None = ...,
    **extra: Annotated[
        Any,
        deprecated("""
            The `extra` kwargs is deprecated. Use `json_schema_extra` instead.
            """),
    ],
) -> Any:
    """
    Args:
        default: Default value if the parameter field is not set.

        default_factory: A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        alias: An alternative name for the parameter field.

            This will be used to extract the data and for the generated OpenAPI.
            It is particularly useful when you can't use the name you want because it
            is a Python reserved keyword or similar.

        alias_priority: Priority of the alias. This affects whether an alias generator is used.

        validation_alias: 'Whitelist' validation step. The parameter field will be the single one
            allowed by the alias or set of aliases defined.

        serialization_alias: 'Blacklist' validation step. The vanilla parameter field will be the
            single one of the alias' or set of aliases' fields and all the other
            fields will be ignored at serialization time.

        title: Human-readable title.

        description: Human-readable description.

        gt: Greater than. If set, value must be greater than this. Only applicable to
            numbers.

        ge: Greater than or equal. If set, value must be greater than or equal to
            this. Only applicable to numbers.

        lt: Less than. If set, value must be less than this. Only applicable to numbers.

        le: Less than or equal. If set, value must be less than or equal to this.
            Only applicable to numbers.

        min_length: Minimum length for strings.

        max_length: Maximum length for strings.

        pattern: RegEx pattern for strings.

        regex: RegEx pattern for strings.

        discriminator: Parameter field name for discriminating the type in a tagged union.

        strict: If `True`, strict validation is applied to the field.

        multiple_of: Value must be a multiple of this. Only applicable to numbers.

        allow_inf_nan: Allow `inf`, `-inf`, `nan`. Only applicable to numbers.

        max_digits: Maximum number of digits allowed for decimal values.

        decimal_places: Maximum number of decimal places allowed for decimal values.

        examples: Example values for this field.

            Read more about it in the
            [FastAPI docs for Declare Request Example Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/)

        openapi_examples: OpenAPI-specific examples.

            It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            Swagger UI (that provides the `/docs` interface) has better support for the
            OpenAPI-specific examples than the JSON Schema `examples`, that's the main
            use case for this.

            Read more about it in the
            [FastAPI docs for Declare Request Example
            Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/#using-the-openapi_examples-parameter).

        deprecated: Mark this parameter field as deprecated.

            It will affect the generated OpenAPI (e.g. visible at `/docs`).

        include_in_schema: To include (or not) this parameter field in the generated OpenAPI.
            You probably don't need it, but it's available.

            This affects the generated OpenAPI (e.g. visible at `/docs`).

        json_schema_extra: Any additional JSON schema data.

        **extra: Include extra fields used by the JSON Schema.
    """

def Body(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | None = ...,
    embed: bool | None = ...,
    media_type: str = ...,
    alias: str | None = ...,
    alias_priority: int | None = ...,
    validation_alias: str | AliasPath | AliasChoices | None = ...,
    serialization_alias: str | None = ...,
    title: str | None = ...,
    description: str | None = ...,
    gt: float | None = ...,
    ge: float | None = ...,
    lt: float | None = ...,
    le: float | None = ...,
    min_length: int | None = ...,
    max_length: int | None = ...,
    pattern: str | None = ...,
    regex: Annotated[
        str | None,
        deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
    ] = ...,
    discriminator: str | None = ...,
    strict: bool | None = ...,
    multiple_of: float | None = ...,
    allow_inf_nan: bool | None = ...,
    max_digits: int | None = ...,
    decimal_places: int | None = ...,
    examples: list[Any] | None = ...,
    example: Annotated[
        Any | None,
        deprecated(
            "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
            "although still supported. Use examples instead."
        ),
    ] = ...,
    openapi_examples: dict[str, Example] | None = ...,
    deprecated: deprecated | str | bool | None = ...,
    include_in_schema: bool = ...,
    json_schema_extra: dict[str, Any] | None = ...,
    **extra: Annotated[
        Any,
        deprecated("""
            The `extra` kwargs is deprecated. Use `json_schema_extra` instead.
            """),
    ],
) -> Any:
    """
    Args:
        default: Default value if the parameter field is not set.

        default_factory: A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        embed: When `embed` is `True`, the parameter will be expected in a JSON body as a
            key instead of being the JSON body itself.

            This happens automatically when more than one `Body` parameter is declared.

            Read more about it in the
            [FastAPI docs for Body - Multiple
            Parameters](https://fastapi.tiangolo.com/tutorial/body-multiple-params/#embed-a-single-body-parameter).

        media_type: The media type of this parameter field. Changing it would affect the
            generated OpenAPI, but currently it doesn't affect the parsing of the data.

        alias: An alternative name for the parameter field.

            This will be used to extract the data and for the generated OpenAPI.
            It is particularly useful when you can't use the name you want because it
            is a Python reserved keyword or similar.

        alias_priority: Priority of the alias. This affects whether an alias generator is used.

        validation_alias: 'Whitelist' validation step. The parameter field will be the single one
            allowed by the alias or set of aliases defined.

        serialization_alias: 'Blacklist' validation step. The vanilla parameter field will be the
            single one of the alias' or set of aliases' fields and all the other
            fields will be ignored at serialization time.

        title: Human-readable title.

        description: Human-readable description.

        gt: Greater than. If set, value must be greater than this. Only applicable to
            numbers.

        ge: Greater than or equal. If set, value must be greater than or equal to
            this. Only applicable to numbers.

        lt: Less than. If set, value must be less than this. Only applicable to numbers.

        le: Less than or equal. If set, value must be less than or equal to this.
            Only applicable to numbers.

        min_length: Minimum length for strings.

        max_length: Maximum length for strings.

        pattern: RegEx pattern for strings.

        regex: RegEx pattern for strings.

        discriminator: Parameter field name for discriminating the type in a tagged union.

        strict: If `True`, strict validation is applied to the field.

        multiple_of: Value must be a multiple of this. Only applicable to numbers.

        allow_inf_nan: Allow `inf`, `-inf`, `nan`. Only applicable to numbers.

        max_digits: Maximum number of digits allowed for decimal values.

        decimal_places: Maximum number of decimal places allowed for decimal values.

        examples: Example values for this field.

            Read more about it in the
            [FastAPI docs for Declare Request Example Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/)

        openapi_examples: OpenAPI-specific examples.

            It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            Swagger UI (that provides the `/docs` interface) has better support for the
            OpenAPI-specific examples than the JSON Schema `examples`, that's the main
            use case for this.

            Read more about it in the
            [FastAPI docs for Declare Request Example
            Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/#using-the-openapi_examples-parameter).

        deprecated: Mark this parameter field as deprecated.

            It will affect the generated OpenAPI (e.g. visible at `/docs`).

        include_in_schema: To include (or not) this parameter field in the generated OpenAPI.
            You probably don't need it, but it's available.

            This affects the generated OpenAPI (e.g. visible at `/docs`).

        json_schema_extra: Any additional JSON schema data.

        **extra: Include extra fields used by the JSON Schema.
    """

def Form(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | None = ...,
    media_type: str = ...,
    alias: str | None = ...,
    alias_priority: int | None = ...,
    validation_alias: str | AliasPath | AliasChoices | None = ...,
    serialization_alias: str | None = ...,
    title: str | None = ...,
    description: str | None = ...,
    gt: float | None = ...,
    ge: float | None = ...,
    lt: float | None = ...,
    le: float | None = ...,
    min_length: int | None = ...,
    max_length: int | None = ...,
    pattern: str | None = ...,
    regex: Annotated[
        str | None,
        deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
    ] = ...,
    discriminator: str | None = ...,
    strict: bool | None = ...,
    multiple_of: float | None = ...,
    allow_inf_nan: bool | None = ...,
    max_digits: int | None = ...,
    decimal_places: int | None = ...,
    examples: list[Any] | None = ...,
    example: Annotated[
        Any | None,
        deprecated(
            "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
            "although still supported. Use examples instead."
        ),
    ] = ...,
    openapi_examples: dict[str, Example] | None = ...,
    deprecated: deprecated | str | bool | None = ...,
    include_in_schema: bool = ...,
    json_schema_extra: dict[str, Any] | None = ...,
    **extra: Annotated[
        Any,
        deprecated("""
            The `extra` kwargs is deprecated. Use `json_schema_extra` instead.
            """),
    ],
) -> Any:
    """
    Args:
        default: Default value if the parameter field is not set.

        default_factory: A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        media_type: The media type of this parameter field. Changing it would affect the
            generated OpenAPI, but currently it doesn't affect the parsing of the data.

        alias: An alternative name for the parameter field.

            This will be used to extract the data and for the generated OpenAPI.
            It is particularly useful when you can't use the name you want because it
            is a Python reserved keyword or similar.

        alias_priority: Priority of the alias. This affects whether an alias generator is used.

        validation_alias: 'Whitelist' validation step. The parameter field will be the single one
            allowed by the alias or set of aliases defined.

        serialization_alias: 'Blacklist' validation step. The vanilla parameter field will be the
            single one of the alias' or set of aliases' fields and all the other
            fields will be ignored at serialization time.

        title: Human-readable title.

        description: Human-readable description.

        gt: Greater than. If set, value must be greater than this. Only applicable to
            numbers.

        ge: Greater than or equal. If set, value must be greater than or equal to
            this. Only applicable to numbers.

        lt: Less than. If set, value must be less than this. Only applicable to numbers.

        le: Less than or equal. If set, value must be less than or equal to this.
            Only applicable to numbers.

        min_length: Minimum length for strings.

        max_length: Maximum length for strings.

        pattern: RegEx pattern for strings.

        regex: RegEx pattern for strings.

        discriminator: Parameter field name for discriminating the type in a tagged union.

        strict: If `True`, strict validation is applied to the field.

        multiple_of: Value must be a multiple of this. Only applicable to numbers.

        allow_inf_nan: Allow `inf`, `-inf`, `nan`. Only applicable to numbers.

        max_digits: Maximum number of digits allowed for decimal values.

        decimal_places: Maximum number of decimal places allowed for decimal values.

        examples: Example values for this field.

            Read more about it in the
            [FastAPI docs for Declare Request Example Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/)

        openapi_examples: OpenAPI-specific examples.

            It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            Swagger UI (that provides the `/docs` interface) has better support for the
            OpenAPI-specific examples than the JSON Schema `examples`, that's the main
            use case for this.

            Read more about it in the
            [FastAPI docs for Declare Request Example
            Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/#using-the-openapi_examples-parameter).

        deprecated: Mark this parameter field as deprecated.

            It will affect the generated OpenAPI (e.g. visible at `/docs`).

        include_in_schema: To include (or not) this parameter field in the generated OpenAPI.
            You probably don't need it, but it's available.

            This affects the generated OpenAPI (e.g. visible at `/docs`).

        json_schema_extra: Any additional JSON schema data.

        **extra: Include extra fields used by the JSON Schema.
    """

def File(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | None = ...,
    media_type: str = ...,
    alias: str | None = ...,
    alias_priority: int | None = ...,
    validation_alias: str | AliasPath | AliasChoices | None = ...,
    serialization_alias: str | None = ...,
    title: str | None = ...,
    description: str | None = ...,
    gt: float | None = ...,
    ge: float | None = ...,
    lt: float | None = ...,
    le: float | None = ...,
    min_length: int | None = ...,
    max_length: int | None = ...,
    pattern: str | None = ...,
    regex: Annotated[
        str | None,
        deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
    ] = ...,
    discriminator: str | None = ...,
    strict: bool | None = ...,
    multiple_of: float | None = ...,
    allow_inf_nan: bool | None = ...,
    max_digits: int | None = ...,
    decimal_places: int | None = ...,
    examples: list[Any] | None = ...,
    example: Annotated[
        Any | None,
        deprecated(
            "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
            "although still supported. Use examples instead."
        ),
    ] = ...,
    openapi_examples: dict[str, Example] | None = ...,
    deprecated: deprecated | str | bool | None = ...,
    include_in_schema: bool = ...,
    json_schema_extra: dict[str, Any] | None = ...,
    **extra: Annotated[
        Any,
        deprecated("""
            The `extra` kwargs is deprecated. Use `json_schema_extra` instead.
            """),
    ],
) -> Any:
    """
    Args:
        default: Default value if the parameter field is not set.

        default_factory: A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.

        media_type: The media type of this parameter field. Changing it would affect the
            generated OpenAPI, but currently it doesn't affect the parsing of the data.

        alias: An alternative name for the parameter field.

            This will be used to extract the data and for the generated OpenAPI.
            It is particularly useful when you can't use the name you want because it
            is a Python reserved keyword or similar.

        alias_priority: Priority of the alias. This affects whether an alias generator is used.

        validation_alias: 'Whitelist' validation step. The parameter field will be the single one
            allowed by the alias or set of aliases defined.

        serialization_alias: 'Blacklist' validation step. The vanilla parameter field will be the
            single one of the alias' or set of aliases' fields and all the other
            fields will be ignored at serialization time.

        title: Human-readable title.

        description: Human-readable description.

        gt: Greater than. If set, value must be greater than this. Only applicable to
            numbers.

        ge: Greater than or equal. If set, value must be greater than or equal to
            this. Only applicable to numbers.

        lt: Less than. If set, value must be less than this. Only applicable to numbers.

        le: Less than or equal. If set, value must be less than or equal to this.
            Only applicable to numbers.

        min_length: Minimum length for strings.

        max_length: Maximum length for strings.

        pattern: RegEx pattern for strings.

        regex: RegEx pattern for strings.

        discriminator: Parameter field name for discriminating the type in a tagged union.

        strict: If `True`, strict validation is applied to the field.

        multiple_of: Value must be a multiple of this. Only applicable to numbers.

        allow_inf_nan: Allow `inf`, `-inf`, `nan`. Only applicable to numbers.

        max_digits: Maximum number of digits allowed for decimal values.

        decimal_places: Maximum number of decimal places allowed for decimal values.

        examples: Example values for this field.

            Read more about it in the
            [FastAPI docs for Declare Request Example Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/)

        openapi_examples: OpenAPI-specific examples.

            It will be added to the generated OpenAPI (e.g. visible at `/docs`).

            Swagger UI (that provides the `/docs` interface) has better support for the
            OpenAPI-specific examples than the JSON Schema `examples`, that's the main
            use case for this.

            Read more about it in the
            [FastAPI docs for Declare Request Example
            Data](https://fastapi.tiangolo.com/tutorial/schema-extra-example/#using-the-openapi_examples-parameter).

        deprecated: Mark this parameter field as deprecated.

            It will affect the generated OpenAPI (e.g. visible at `/docs`).

        include_in_schema: To include (or not) this parameter field in the generated OpenAPI.
            You probably don't need it, but it's available.

            This affects the generated OpenAPI (e.g. visible at `/docs`).

        json_schema_extra: Any additional JSON schema data.

        **extra: Include extra fields used by the JSON Schema.
    """

def Depends(
    dependency: Callable[..., Any] | None = ...,
    *,
    use_cache: bool = ...,
    scope: Literal["function", "request"] | None = ...,
) -> Any:
    """
    Declare a FastAPI dependency.

    It takes a single "dependable" callable (like a function).

    Don't call it directly, FastAPI will call it for you.

    Read more about it in the
    [FastAPI docs for Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/).

    **Example**

    ```python
    from typing import Annotated

    from fastapi import Depends, FastAPI

    app = FastAPI()


    async def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
        return {"q": q, "skip": skip, "limit": limit}


    @app.get("/items/")
    async def read_items(commons: Annotated[dict, Depends(common_parameters)]):
        return commons
    ```

    Args:
        dependency: A "dependable" callable (like a function).

            Don't call it directly, FastAPI will call it for you, just pass the object
            directly.

            Read more about it in the
            [FastAPI docs for Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)

        use_cache: By default, after a dependency is called the first time in a request, if
            the dependency is declared again for the rest of the request (for example
            if the dependency is needed by several dependencies), the value will be
            re-used for the rest of the request.

            Set `use_cache` to `False` to disable this behavior and ensure the
            dependency is called again (if declared more than once) in the same request.

            Read more about it in the
            [FastAPI docs about
            sub-dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/#using-the-same-dependency-multiple-times)

        scope: Mainly for dependencies with `yield`, define when the dependency function
            should start (the code before `yield`) and when it should end (the code
            after `yield`).

            * `"function"`: start the dependency before the *path operation function*
                that handles the request, end the dependency after the *path operation
                function* ends, but **before** the response is sent back to the client.
                So, the dependency function will be executed **around** the *path operation
                **function***.
            * `"request"`: start the dependency before the *path operation function*
                that handles the request (similar to when using `"function"`), but end
                **after** the response is sent back to the client. So, the dependency
                function will be executed **around** the **request** and response cycle.

            Read more about it in the
            [FastAPI docs for FastAPI Dependencies with
            yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope)
    """

def Security(
    dependency: Callable[..., Any] | None = ..., *, scopes: Sequence[str] | None = ..., use_cache: bool = ...
) -> Any:
    """
    Declare a FastAPI Security dependency.

    The only difference with a regular dependency is that it can declare OAuth2
    scopes that will be integrated with OpenAPI and the automatic UI docs (by default
    at `/docs`).

    It takes a single "dependable" callable (like a function).

    Don't call it directly, FastAPI will call it for you.

    Read more about it in the
    [FastAPI docs for Security](https://fastapi.tiangolo.com/tutorial/security/) and
    in the
    [FastAPI docs for OAuth2 scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/).

    **Example**

    ```python
    from typing import Annotated

    from fastapi import Security, FastAPI

    from .db import User
    from .security import get_current_active_user

    app = FastAPI()

    @app.get("/users/me/items/")
    async def read_own_items(
        current_user: Annotated[User, Security(get_current_active_user, scopes=["items"])]
    ):
        return [{"item_id": "Foo", "owner": current_user.username}]
    ```

    Args:
        dependency: A "dependable" callable (like a function).

            Don't call it directly, FastAPI will call it for you, just pass the object
            directly.

            Read more about it in the
            [FastAPI docs for Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)

        scopes: OAuth2 scopes required for the *path operation* that uses this Security
            dependency.

            The term "scope" comes from the OAuth2 specification, it seems to be
            intentionally vague and interpretable. It normally refers to permissions,
            in cases to roles.

            These scopes are integrated with OpenAPI (and the API docs at `/docs`).
            So they are visible in the OpenAPI specification.

            Read more about it in the
            [FastAPI docs about OAuth2 scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/)

        use_cache: By default, after a dependency is called the first time in a request, if
            the dependency is declared again for the rest of the request (for example
            if the dependency is needed by several dependencies), the value will be
            re-used for the rest of the request.

            Set `use_cache` to `False` to disable this behavior and ensure the
            dependency is called again (if declared more than once) in the same request.

            Read more about it in the
            [FastAPI docs about
            sub-dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/#using-the-same-dependency-multiple-times)
    """
