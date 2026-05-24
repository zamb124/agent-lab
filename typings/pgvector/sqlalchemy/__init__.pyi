from collections.abc import Sequence

from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import UserDefinedType

class VECTOR(UserDefinedType[list[float]]):
    cache_ok: bool
    dim: int | None

    def __init__(self, dim: int | None = None) -> None: ...

    class comparator_factory(UserDefinedType.Comparator[list[float]]):
        def l2_distance(self, other: Sequence[float]) -> ColumnElement[float]: ...
        def max_inner_product(self, other: Sequence[float]) -> ColumnElement[float]: ...
        def cosine_distance(self, other: Sequence[float]) -> ColumnElement[float]: ...
        def l1_distance(self, other: Sequence[float]) -> ColumnElement[float]: ...


Vector = VECTOR
