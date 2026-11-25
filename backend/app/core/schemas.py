"""Base schema: camelCase JSON on the wire, snake_case in Python."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class Page[T](APIModel):
    """One page of results. Pass `nextCursor` back as `cursor` to get the next page."""

    items: list[T]
    next_cursor: str | None = None
