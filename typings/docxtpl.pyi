from io import BytesIO

from jinja2 import Environment

from core.types import JsonObject

class DocxTemplate:
    def __init__(self, template_file: BytesIO) -> None: ...

    def get_undeclared_template_variables(
        self,
        *,
        jinja_env: Environment,
        context: JsonObject | None = None,
    ) -> set[str]: ...

    def render(
        self,
        context: JsonObject,
        *,
        jinja_env: Environment,
        autoescape: bool,
    ) -> None: ...

    def save(self, filename: BytesIO) -> None: ...


class RichText: ...


class InlineImage: ...
