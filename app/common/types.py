from enum import Enum
from typing import Type

from sqlalchemy import Enum as SAEnum


def enum_col(enum_cls: Type[Enum], length: int = 30) -> SAEnum:
    """Store enums as VARCHAR (not native PG ENUM) -> painless Alembic migrations,
    persisting the enum *value* rather than its name."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
