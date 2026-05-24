"""
Apple (Sign in with Apple) OAuth провайдер — веб-флоу authorization code.
"""

import time
from typing import cast as type_cast
from typing import override
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient

from core.config.models import AuthProviderConfig
from core.http import request_public_oauth
from core.identity.base_provider import BaseAuthProvider
from core.logging import get_logger
from core.models.identity_models import AuthProvider, ProviderUserInfo
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_AUDIENCE_FOR_SECRET = "https://appleid.apple.com"
DEFAULT_AUTH_URL = "https://appleid.apple.com/auth/authorize"
DEFAULT_TOKEN_URL = "https://appleid.apple.com/auth/token"
DEFAULT_SCOPE = "name email"


def _normalize_apple_pem(raw: str) -> str:
    text = raw.strip().replace("\\n", "\n")
    if "BEGIN PRIVATE KEY" not in text:
        raise ValueError("apple_private_key должен быть PEM (BEGIN PRIVATE KEY)")
    return text


def build_apple_client_secret(
    team_id: str,
    client_id: str,
    key_id: str,
    private_key_pem: str,
    ttl_seconds: int = 3600,
) -> str:
    now = int(time.time())
    headers = {"kid": key_id, "alg": "ES256"}
    payload = {
        "iss": team_id,
        "iat": now,
        "exp": now + ttl_seconds,
        "aud": APPLE_AUDIENCE_FOR_SECRET,
        "sub": client_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="ES256", headers=headers)


def decode_apple_id_token(id_token: str, audience: str) -> JsonObject:
    jwks_client = PyJWKClient(APPLE_JWKS_URL)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    return require_json_object(
        type_cast(
            JsonValue,
            jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=APPLE_ISSUER,
            ),
        ),
        "apple.id_token.claims",
    )


def _name_from_apple_user_json(user_json: str) -> str | None:
    parsed = parse_json_object(user_json, "apple.user_json")
    name_obj = parsed.get("name")
    if name_obj is None:
        return None
    name_data = require_json_object(name_obj, "apple.user_json.name")
    first_value = name_data.get("firstName")
    if first_value is not None and not isinstance(first_value, str):
        raise ValueError("Apple user_json.name.firstName must be a string")
    last_value = name_data.get("lastName")
    if last_value is not None and not isinstance(last_value, str):
        raise ValueError("Apple user_json.name.lastName must be a string")
    first = "" if first_value is None else first_value.strip()
    last = "" if last_value is None else last_value.strip()
    combined = f"{first} {last}".strip()
    return combined if combined else None


class AppleProvider(BaseAuthProvider):
    """Провайдер Sign in with Apple (OAuth 2.0, Services ID как client_id)."""

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.APPLE, config)
        self.auth_url: str = DEFAULT_AUTH_URL if not self.auth_url else self.auth_url
        self.token_url: str = DEFAULT_TOKEN_URL if not self.token_url else self.token_url
        self.scope: str = (
            DEFAULT_SCOPE if not self.scope or self.scope == "openid profile email" else self.scope
        )
        raw_key = config.apple_private_key
        self._private_key_pem: str | None = (
            _normalize_apple_pem(raw_key) if raw_key is not None and raw_key.strip() else None
        )
        self._team_id: str | None = config.apple_team_id
        self._key_id: str | None = config.apple_key_id

    @override
    def validate_config(self) -> bool:
        if not self.config.enabled:
            logger.warning("Провайдер apple отключен")
            return False
        if not self.client_id:
            logger.warning("client_id (Services ID) не настроен для apple")
            return False
        if not self._team_id:
            logger.warning("apple_team_id не настроен для apple")
            return False
        if not self._key_id:
            logger.warning("apple_key_id не настроен для apple")
            return False
        if not self.config.apple_private_key:
            logger.warning("apple_private_key не настроен для apple")
            return False
        try:
            _ = _normalize_apple_pem(self.config.apple_private_key)
        except ValueError as e:
            logger.warning("apple_private_key некорректен: %s", e)
            return False
        if not self.auth_url or not self.token_url:
            logger.warning("auth_url или token_url не заданы для apple")
            return False
        return True

    @override
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        if not self.client_id:
            raise ValueError("client_id (Services ID) не настроен для apple")
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
            "response_mode": "form_post",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    @override
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> tuple[str, str | None]:
        if not self.client_id:
            raise ValueError("client_id (Services ID) не настроен для apple")
        if not self._team_id:
            raise ValueError("apple_team_id не настроен для apple")
        if not self._key_id:
            raise ValueError("apple_key_id не настроен для apple")
        if not self._private_key_pem:
            raise ValueError("apple_private_key не настроен для apple")
        client_secret = build_apple_client_secret(
            self._team_id,
            self.client_id,
            self._key_id,
            self._private_key_pem,
        )
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": client_secret,
        }
        response = await request_public_oauth(
            "POST",
            self.token_url,
            timeout=30.0,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            logger.error("Ошибка токена Apple: %s", response.text)
            raise ValueError(f"Apple вернул ошибку: {response.status_code}")
        token_data = parse_json_object(response.content, "apple.token.response")
        id_token = token_data.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise ValueError("Apple не вернул id_token")
        refresh_token = token_data.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise ValueError("Apple вернул refresh_token не строкой")
        return id_token, refresh_token

    @override
    async def get_user_info(
        self,
        access_token: str,
        first_login_user_json: str | None = None,
    ) -> ProviderUserInfo:
        if not self.client_id:
            raise ValueError("client_id (Services ID) не настроен для apple")
        claims = decode_apple_id_token(access_token, self.client_id)
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise ValueError("Apple id_token без sub")

        email_value = claims.get("email")
        if not isinstance(email_value, str) or not email_value.strip():
            raise ValueError("Apple id_token без email")
        email = email_value.strip()

        name = ""
        if first_login_user_json:
            parsed_name = _name_from_apple_user_json(first_login_user_json)
            if parsed_name:
                name = parsed_name

        if not name and email:
            name = email.split("@")[0]
        if not name:
            name = sub

        return ProviderUserInfo(
            provider_user_id=sub,
            email=email,
            name=name,
            avatar_url=None,
            raw_data=claims,
        )
