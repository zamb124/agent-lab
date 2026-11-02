"""OAuth2/OIDC identity-провайдеры: Yandex ID, VK ID, Sber ID.

Общий каркас `_OAuthIdProvider`: `authorization_url` + `fetch_phones`
(code → token → userinfo → phones). Каждый провайдер знает свои endpoint'ы
и маппинг полей; креды — `CustomerAuthOAuthClientConfig` из бренда.

Регистрация приложений (док. — `.cursor/rules/customers.mdc` § Провайдеры):
- Yandex: https://oauth.yandex.ru → «Веб-сервисы», redirect URI колбэка,
  права «Номер телефона» (яндекс отдаёт `default_phone.number`).
- VK ID: https://id.vk.ru/about/business/go/console → PKCE-флоу
  (`code_challenge`), scope `phone` (отдаёт `user.phone`).
- Sber ID: https://developers.sber.ru → OIDC, scope `openid phone`
  (отдаёт claim `phone_number` в userinfo).
"""

from __future__ import annotations

from typing import ClassVar, override
from urllib.parse import urlencode

from core.config.models import CustomerAuthOAuthClientConfig
from core.customers.contracts import DirectVerificationRequest, ProviderPhone
from core.customers.enums import (
    CustomerIdentityProvider,
    DirectAuthorizationKind,
    PhoneVerificationErrorCode,
    PhoneVerificationMethod,
)
from core.customers.errors import ProviderError
from core.customers.phone import normalize_phone_e164
from core.http.client import request_public_oauth
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_object,
)


class _OAuthIdProvider:
    provider: ClassVar[CustomerIdentityProvider]
    method: ClassVar[PhoneVerificationMethod]
    direct_kind: ClassVar[DirectAuthorizationKind] = DirectAuthorizationKind.OAUTH
    _authorize_url: ClassVar[str]
    _token_url: ClassVar[str]
    _userinfo_url: ClassVar[str]
    _scope: ClassVar[str]

    def __init__(self, cfg: CustomerAuthOAuthClientConfig | None) -> None:
        self._cfg: CustomerAuthOAuthClientConfig | None = cfg

    def available(self) -> bool:
        c = self._cfg
        return bool(c is not None and c.enabled and c.client_id and c.client_secret)

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        assert self._cfg is not None
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._cfg.client_id,
                "redirect_uri": redirect_uri,
                "scope": self._scope,
                "state": state,
            }
        )
        return f"{self._authorize_url}?{query}"

    def _token_params(
        self, proof: DirectVerificationRequest, client_id: str, client_secret: str
    ) -> dict[str, str]:
        return {
            "grant_type": "authorization_code",
            "code": proof.oauth_code or "",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": proof.redirect_uri or "",
        }

    def _userinfo_headers(self, access_token: str) -> dict[str, str]:
        return {"Authorization": f"OAuth {access_token}"}

    def _extract_phones(self, _data: JsonObject) -> list[str]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def fetch_phones(
        self, proof: DirectVerificationRequest
    ) -> list[ProviderPhone]:
        c = self._cfg
        if c is None or not (c.client_id and c.client_secret):
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        if not proof.oauth_code:
            raise ProviderError(
                PhoneVerificationErrorCode.CODE_INVALID, "oauth_code is required"
            )
        try:
            token_resp = await request_public_oauth(
                "POST",
                self._token_url,
                data=self._token_params(proof, c.client_id, c.client_secret),
                timeout=20.0,
            )
            token_body = parse_json_object(token_resp.text, f"{self.provider}.token")
            access_token = str(token_body.get("access_token") or "")
            if not access_token:
                raise ProviderError(
                    PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                    f"{self.provider}: no access_token",
                )
            info_resp = await request_public_oauth(
                "GET",
                self._userinfo_url,
                headers=self._userinfo_headers(access_token),
                timeout=20.0,
            )
            info = parse_json_object(info_resp.text, f"{self.provider}.userinfo")
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                f"{self.provider}: {exc}",
                retryable=True,
            ) from exc
        phones: list[ProviderPhone] = []
        for raw in self._extract_phones(info):
            normalized = normalize_phone_e164(raw)
            if normalized is not None:
                phones.append(ProviderPhone(phone_e164=normalized, verified=True))
        if not phones:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_MISMATCH,
                f"{self.provider}: account has no verified phone",
            )
        phones[0].default = True
        return phones


class YandexIdProvider(_OAuthIdProvider):
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.YANDEX
    method: ClassVar[PhoneVerificationMethod] = PhoneVerificationMethod.YANDEX_ID
    _authorize_url: ClassVar[str] = "https://oauth.yandex.ru/authorize"
    _token_url: ClassVar[str] = "https://oauth.yandex.ru/token"
    _userinfo_url: ClassVar[str] = "https://login.yandex.ru/info"
    _scope: ClassVar[str] = "login:info"

    @override
    def _extract_phones(self, data: JsonObject) -> list[str]:
        default_phone = data.get("default_phone")
        if isinstance(default_phone, dict):
            phone = require_json_object(default_phone, "yandex.default_phone")
            number = phone.get("number")
            return [str(number)] if number else []
        phones = data.get("phones")
        if isinstance(phones, list):
            return [
                str(p["number"])
                for p in phones
                if isinstance(p, dict) and p.get("number")
            ]
        return []


class VkIdProvider(_OAuthIdProvider):
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.VK
    method: ClassVar[PhoneVerificationMethod] = PhoneVerificationMethod.VK_ID
    _authorize_url: ClassVar[str] = "https://id.vk.ru/authorize"
    _token_url: ClassVar[str] = "https://id.vk.ru/oauth2/auth"
    _userinfo_url: ClassVar[str] = "https://id.vk.ru/oauth2/user_info"
    _scope: ClassVar[str] = "phone"

    @override
    def _extract_phones(self, data: JsonObject) -> list[str]:
        user = data.get("user")
        if isinstance(user, dict):
            phone = require_json_object(user, "vk.user").get("phone")
            return [str(phone)] if phone else []
        return []


class SberIdProvider(_OAuthIdProvider):
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.SBER
    method: ClassVar[PhoneVerificationMethod] = PhoneVerificationMethod.SBER_ID
    _authorize_url: ClassVar[str] = "https://id.sber.ru/oidc/authorize"
    _token_url: ClassVar[str] = "https://id.sber.ru/oidc/token"
    _userinfo_url: ClassVar[str] = "https://id.sber.ru/oidc/userinfo"
    _scope: ClassVar[str] = "openid phone"

    @override
    def _userinfo_headers(self, access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    @override
    def _extract_phones(self, data: JsonObject) -> list[str]:
        phone: JsonValue | None = data.get("phone_number")
        return [str(phone)] if phone else []
