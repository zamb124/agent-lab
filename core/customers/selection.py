"""Автоматический выбор методов подтверждения (customers.mdc).

`select_methods_by_priority_asc` строит список `MethodOption` из `method_priority` конфига:
показываем только реально доступные каналы бренда; SMS-код — единый метод
поверх каскада отправителей (real → emulator); эмуляторный direct — `auto`.
"""

from __future__ import annotations

from typing import Literal

from core.clients.phone_verification.base import CodeSender
from core.clients.phone_verification.registry import PhoneVerificationRegistry
from core.config.models import CustomerAuthConfig
from core.customers.contracts import MethodOption
from core.customers.enums import (
    ClientKind,
    CustomerIdentityProvider,
    PhoneVerificationMethod,
)

MethodUi = Literal["deep_link", "oauth", "contact_share", "code_input", "auto"]


def available_code_senders(
    registry: PhoneVerificationRegistry,
) -> list[CodeSender]:
    """Реальные отправители кода, затем эмулятор (фолбек последним)."""
    return [s for s in registry.code_senders if s.available()]


def select_methods_by_priority_asc(
    cfg: CustomerAuthConfig,
    registry: PhoneVerificationRegistry,
    *,
    client: ClientKind,
) -> list[MethodOption]:
    """Список способов для UI: только доступные, в порядке `method_priority`.

    OAuth-методы на `web_desktop` получают +1 к приоритету (вкладка удобнее),
    contact_share — +1 на мобильных (мессенджер под рукой).
    """
    senders = available_code_senders(registry)
    options: list[MethodOption] = []
    for idx, raw in enumerate(cfg.method_priority):
        try:
            method = PhoneVerificationMethod(raw)
        except ValueError:
            continue
        boost = 0
        ui: MethodUi = "code_input"
        if method in registry.contact_share:
            if not registry.contact_share[method].available():
                continue
            ui = "contact_share"
            boost = -1 if client != ClientKind.WEB_DESKTOP else 0
        elif method in registry.oauth:
            if not registry.oauth[method].available():
                continue
            ui = "oauth"
            boost = -1 if client == ClientKind.WEB_DESKTOP else 0
        elif method == PhoneVerificationMethod.SMS_CODE:
            if not senders or not cfg.sms_fallback_enabled:
                continue
            ui = "code_input"
        else:
            continue
        provider: CustomerIdentityProvider | None = None
        for verifier in registry.direct_verifiers:
            if verifier.method == method:
                provider = verifier.provider
                break
        options.append(
            MethodOption(
                kind=method,
                ui=ui,
                priority=idx + boost,
                provider=provider,
            )
        )
    emulator = registry.direct_for(CustomerIdentityProvider.EMULATOR)
    if emulator is not None and emulator.available():
        options.append(
            MethodOption(
                kind=PhoneVerificationMethod.EMULATOR,
                ui="auto",
                priority=len(cfg.method_priority) + 1,
                provider=emulator.provider,
            )
        )
    options.sort(key=lambda option: option.priority)
    return options
