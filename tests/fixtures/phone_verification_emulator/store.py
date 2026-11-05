"""In-memory состояние эмулятора провайдеров верификации телефона."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.types import JsonObject


@dataclass
class OAuthAccount:
    """Аккаунт пользователя у identity-провайдера."""

    user_id: str
    phone: str | None
    first_name: str = "Иван"
    last_name: str = "Иванов"


@dataclass
class ProviderEmulatorStore:
    """Записанные вызовы + мутируемое состояние провайдеров."""

    # Telegram: тела sendMessage, очередь getUpdates, счётчик deleteWebhook
    telegram_messages: list[JsonObject] = field(default_factory=list)
    telegram_updates: list[JsonObject] = field(default_factory=list)
    telegram_webhook_deleted: int = 0
    # MAX: (query params, body) POST /messages; Authorization header последних вызовов
    max_messages: list[tuple[dict[str, str], JsonObject]] = field(default_factory=list)
    max_authorization: list[str] = field(default_factory=list)
    max_access_token: str = ""
    # SMS.RU: query params /sms/send
    sms_requests: list[dict[str, str]] = field(default_factory=list)
    # OAuth: authorize-запросы по провайдеру
    authorize_requests: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    token_requests: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    # provider -> аккаунт "залогиненного" пользователя
    oauth_accounts: dict[str, OAuthAccount] = field(default_factory=dict)
    # код -> (provider, state, code_challenge)
    auth_codes: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    # access_token -> provider
    access_tokens: dict[str, str] = field(default_factory=dict)
    # Флаги отказов: provider -> HTTP error на token endpoint
    oauth_token_fail: dict[str, int] = field(default_factory=dict)
    # SMS.RU: форсированные status_code (top-level / inner sms)
    sms_top_status_code: int | None = None
    sms_inner_status_code: int | None = None
    # provider -> (client_id, client_secret), которые эмулятор принимает
    client_credentials: dict[str, tuple[str, str]] = field(default_factory=dict)
    # provider -> множество допустимых scope; запрос вне их → error=invalid_scope
    allowed_scopes: dict[str, set[str]] = field(default_factory=dict)
    _counter: int = 0

    def next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def seed_oauth(self, provider: str, *, phone: str | None, user_id: str) -> None:
        self.oauth_accounts[provider] = OAuthAccount(user_id=user_id, phone=phone)
