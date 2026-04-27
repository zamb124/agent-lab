"""
Типы запросов и ответов Browser Runtime (контракт §17 TARGET_ARCHITECTURE_RU).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Optional

PageMode = Literal["interactive", "crawl", "lite"]
SessionMode = Literal["warm", "restore"]

SELECTOR_PREFIX = "selector:"


@dataclass(frozen=True)
class ContextSignature:
    """
    Сигнатура изоляции браузерного контекста (§30.3).
    Без task_id и прочих эфемерных полей.

    Мотивация:
    - Сделать ключ кэширования контекста детерминированным и зависящим только от
      реально влияющих параметров.

    Переиспользование:
    - Стоит: всегда, когда нужен управляемый реюз/изоляция контекстов.
    """

    proxy_policy: str
    shared_storage_key: Optional[str]
    anti_bot_tier: str
    stealth_init_version: str
    locale: str
    timezone_id: str
    user_agent: Optional[str]
    page_mode: PageMode
    permissions_fingerprint: str

    def stable_hash(self) -> str:
        payload = json.dumps(
            {
                "proxy_policy": self.proxy_policy,
                "shared_storage_key": self.shared_storage_key,
                "anti_bot_tier": self.anti_bot_tier,
                "stealth_init_version": self.stealth_init_version,
                "locale": self.locale,
                "timezone_id": self.timezone_id,
                "user_agent": self.user_agent,
                "page_mode": self.page_mode,
                "permissions_fingerprint": self.permissions_fingerprint,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass
class BrowserAcquireRequest:
    """
    Входной контракт операции acquire.

    Связи:
    - Формируется HTTP-слоем и передаётся в `BrowserInteractor.acquire`.

    Инварианты:
    - Должен содержать `endpoint_key` и `context_signature`.
    - `session_mode` определяет стратегию жизненного цикла контекста после release.

    Мотивация:
    - Свести все параметры выдачи страницы в единый DTO.

    Переиспользование:
    - Стоит: как каноничный вход для любых interactor-реализаций.
    """
    run_id: str
    task_id: str
    session_id: str
    page_mode: PageMode
    shared_storage_key: Optional[str]
    proxy_policy: str
    anti_bot_tier: str
    timeout_ms: int
    endpoint_key: str
    session_mode: SessionMode
    restore_state_key: Optional[str]
    context_signature: ContextSignature


@dataclass
class BrowserAcquireResult:
    """
    Результат acquire: выделенные page/context и служебные метаданные сессии.

    Связи:
    - Возвращается interactor-ом в control adapter и далее в HTTP API.

    Инварианты:
    - `context_signature_hash` соответствует сигнатуре запроса, а `endpoint_key` — фактически использованному endpoint-у.

    Мотивация:
    - Вернуть не только page/context, но и служебные признаки (cold_start/hash),
      нужные orchestration и API.

    Переиспользование:
    - Стоит: как стандартный выход acquire вне зависимости от backend-а.
    """
    page: Any
    context: Any
    browser_id: str
    proxy_id: Optional[str]
    cold_start: bool
    endpoint_key: str
    context_signature_hash: str


@dataclass
class BrowserFetchRequest:
    """
    Входной контракт fetch/navigation.

    Связи:
    - Формируется из `navigate` endpoint-а и исполняется interactor-ом.

    Инварианты:
    - `wait_policy` должен быть поддержан реализацией interactor.
    - Флаги артефактов определяют, какие файлы должны быть сохранены на диск.

    Мотивация:
    - Формализовать навигацию и артефактную политику в одном объекте.

    Переиспользование:
    - Стоит: для любого пути fetch/navigation, включая тесты и API.
    """
    url: str
    wait_policy: str
    screenshot: bool
    snapshot: bool
    capture_pdf: bool
    navigation_timeout_ms: int


@dataclass
class BrowserFetchResult:
    """
    Результат fetch/navigation в нормализованном виде.

    Связи:
    - Используется control API как стабильный ответ на `navigate`.

    Инварианты:
    - Артефактные ссылки либо `None`, либо путь к созданному артефакту.
    - `final_url` всегда отражает текущее значение `page.url` после навигации.

    Мотивация:
    - Нужен стабильный envelope результата навигации без зависимости от движка.

    Переиспользование:
    - Стоит: как внешний контракт control API и внутренних пайплайнов.
    """
    final_url: str
    status_code: Optional[int]
    response_headers: dict[str, str]
    html: Optional[str]
    screenshot_ref: Optional[str]
    pdf_ref: Optional[str]
    snapshot_ref: Optional[str]
    anti_bot_signals: dict[str, Any]


@dataclass
class SessionStateBlob:
    """
    Сериализованное состояние сессии для restore-сценария.

    Связи:
    - Хранится в `SessionStateStore` и используется в `save_state/restore_state`.

    Инварианты:
    - `storage_state` пригоден для `browser.new_context(storage_state=...)`.
    - `session_storage_by_origin` хранит значения строго по origin.

    Мотивация:
    - Отделить сериализуемое состояние сессии от runtime-объектов Playwright.

    Переиспользование:
    - Стоит: как переносимый формат save/restore.
    """
    shared_storage_key: str
    storage_state: dict[str, Any]
    session_storage_by_origin: dict[str, dict[str, str]]
    current_url: str
    proxy_policy: str
    anti_bot_tier: str
    locale: str
    timezone_id: str
    user_agent: Optional[str]
    page_mode: PageMode
    permissions_fingerprint: str
    last_snapshot_ref: Optional[str]
    pause_ttl_soft_sec: Optional[int] = None
    pause_ttl_hard_sec: Optional[int] = None


@dataclass
class ExecCodeResult:
    """
    Нормализованный результат выполнения action-кода в sandbox.

    Связи:
    - Формируется interactor-ом и сериализуется adapter-ом в ответ `/action`.

    Инварианты:
    - При `ok=False` поле `error` содержит диагностическую причину.

    Мотивация:
    - Нормализовать ответ sandbox-исполнения для API/оркестратора.

    Переиспользование:
    - Стоит: для любых backend-ов, которые поддерживают action/exec.
    """
    ok: bool
    stdout: str
    console_events: list[dict[str, Any]]
    dom_diff_ref: Optional[str]
    error: Optional[str]


ControlBackend = Literal["playwright", "browser_use", "agent_browser"]


@dataclass
class BrowserRuntimeSettingsView:
    """
    Срез настроек runtime без жёсткой привязки к pydantic-слою.

    Связи:
    - Используется при сборке `BrowserRuntimeFacade` и всех runtime-компонентов.

    Инварианты:
    - `cdp_urls_by_endpoint` должен содержать хотя бы один endpoint.
    - `default_endpoint_key` должен указывать на существующий ключ endpoint-а.

    Мотивация:
    - Изолировать runtime-код от pydantic и загрузчика конфигов.

    Переиспользование:
    - Стоит: передавать в runtime как единственный источник настроек.
    """

    default_endpoint_key: str
    cdp_urls_by_endpoint: dict[str, str]
    artifacts_dir: str
    default_page_ttl_sec: int
    warm_idle_sec: int
    init_scripts_version: str
    control_backend: ControlBackend
