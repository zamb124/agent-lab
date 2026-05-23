from __future__ import annotations

from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import User


def test_context_keeps_language_enum_for_runtime_and_serializes_value() -> None:
    ctx = Context(user=User(user_id="u_ctx_lang", name="User"), language=Language.RU)

    assert ctx.language is Language.RU
    assert ctx.to_dict()["language"] == "ru"
    assert Context.from_dict(ctx.to_dict()).language is Language.RU
