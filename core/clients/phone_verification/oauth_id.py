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

import uuid
from typing import ClassVar, override
from urllib.parse import urlencode

from core.clients.phone_verification.base import credential_configured
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
        return bool(
            c is not None
            and c.enabled
            and credential_configured(c.client_id)
            and credential_configured(c.client_secret)
        )

    def _endpoint(self, override: str, default: str) -> str:
        return override or default

    def authorization_url(
        self,
        *,
        state: str,
        redirect_uri: str,
        code_challenge: str | None = None,
    ) -> str:
        assert self._cfg is not None
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self._cfg.client_id,
            "redirect_uri": redirect_uri,
            "scope": self._scope,
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        params.update(self._authorize_extra_params(state))
        query = urlencode(params)
        return f"{self._endpoint(self._cfg.authorize_url, self._authorize_url)}?{query}"

    def _authorize_extra_params(self, _state: str) -> dict[str, str]:
        return {}

    def _token_params(
        self, proof: DirectVerificationRequest, client_id: str, client_secret: str
    ) -> dict[str, str]:
        params = {
            "grant_type": "authorization_code",
            "code": proof.oauth_code or "",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": proof.redirect_uri or "",
        }
        if proof.oauth_code_verifier:
            params["code_verifier"] = proof.oauth_code_verifier
        return params

    def _token_headers(self) -> dict[str, str]:
        return {}

    def _userinfo_headers(self, access_token: str) -> dict[str, str]:
        return {"Authorization": f"OAuth {access_token}"}

    def _userinfo_params(self) -> dict[str, str]:
        return {}

    async def _request_userinfo(self, url: str, access_token: str) -> JsonObject:
        assert self._cfg is not None
        resp = await request_public_oauth(
            "GET",
            url,
            headers=self._userinfo_headers(access_token),
            params=self._userinfo_params(),
            timeout=20.0,
        )
        return parse_json_object(resp.text, f"{self.provider}.userinfo")

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
                self._endpoint(c.token_url, self._token_url),
                data=self._token_params(proof, c.client_id, c.client_secret),
                headers=self._token_headers(),
                timeout=20.0,
            )
            token_body = parse_json_object(token_resp.text, f"{self.provider}.token")
            access_token = str(token_body.get("access_token") or "")
            if not access_token:
                raise ProviderError(
                    PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                    f"{self.provider}: no access_token",
                )
            info = await self._request_userinfo(
                self._endpoint(c.userinfo_url, self._userinfo_url), access_token
            )
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
    def _userinfo_params(self) -> dict[str, str]:
        # login.yandex.ru/info отдаёт JSON только с явным format=json.
        return {"format": "json"}

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
    def _token_params(
        self, proof: DirectVerificationRequest, client_id: str, client_secret: str
    ) -> dict[str, str]:
        # VK ID требует device_id и state из authorize-redirect при обмене кода.
        params = super()._token_params(proof, client_id, client_secret)
        if not proof.oauth_device_id:
            raise ProviderError(
                PhoneVerificationErrorCode.CODE_INVALID, "vk: device_id is required"
            )
        params["device_id"] = proof.oauth_device_id
        params["state"] = proof.oauth_state or ""
        return params

    @override
    async def _request_userinfo(self, url: str, access_token: str) -> JsonObject:
        """`POST /oauth2/user_info` — access_token в теле формы (док. VK ID)."""
        assert self._cfg is not None
        resp = await request_public_oauth(
            "POST",
            url,
            data={"client_id": self._cfg.client_id, "access_token": access_token},
            timeout=20.0,
        )
        return parse_json_object(resp.text, f"{self.provider}.userinfo")

    @override
    def _extract_phones(self, data: JsonObject) -> list[str]:
        user = data.get("user")
        if isinstance(user, dict):
            phone = require_json_object(user, "vk.user").get("phone")
            return [str(phone)] if phone else []
        return []


class SberIdProvider(_OAuthIdProvider):
    """Sber ID OIDC (developers.sber.ru/docs/ru/sberid):
    authorize — `id.sber.ru/CSAFront/oidc/authorize.do` (nonce и state
    обязательны), back-channel — `oauth.sber.ru/ru/prod/…` с обязательными
    заголовками `rquid` / `x-introspect-rquid` (32-символьный id сообщения).
    Token/userinfo дополнительно требуют клиентский сертификат партнёра (mTLS)
    — настраивается инфраструктурой, см. customers.mdc."""

    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.SBER
    method: ClassVar[PhoneVerificationMethod] = PhoneVerificationMethod.SBER_ID
    _authorize_url: ClassVar[str] = "https://id.sber.ru/CSAFront/oidc/authorize.do"
    _token_url: ClassVar[str] = "https://oauth.sber.ru/ru/prod/tokens/v2/oidc"
    _userinfo_url: ClassVar[str] = "https://oauth.sber.ru/ru/prod/sberbankid/v2.1/userinfo"
    _scope: ClassVar[str] = "openid phone"

    @override
    def _authorize_extra_params(self, state: str) -> dict[str, str]:
        # `nonce` и `client_type` обязательны по контракту Сбер ID.
        return {"nonce": state, "client_type": "PRIVATE"}

    @override
    def _token_headers(self) -> dict[str, str]:
        return {"accept": "application/json", "rquid": uuid.uuid4().hex}

    @override
    def _userinfo_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "x-introspect-rquid": uuid.uuid4().hex,
        }

    @override
    def _extract_phones(self, data: JsonObject) -> list[str]:
        phone: JsonValue | None = data.get("phone_number")
        return [str(phone)] if phone else []
