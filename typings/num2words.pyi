from typing import Literal

Num2WordsMode = Literal["cardinal", "ordinal"]


def num2words(
    number: int | float | str,
    ordinal: bool = False,
    lang: str = "en",
    to: Num2WordsMode = "cardinal",
) -> str: ...
