"""
Apple (Sign in with Apple) OAuth провайдер — веб-флоу authorization code.
"""

import json
import time
from typing import Any, Optional, Tuple
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient

from core.config.models import AuthProviderConfig
from core.http import request_public_oauth
from core.identity.base_provider import BaseAuthProvider
from core.logging import get_logger
from core.models.identity_models import AuthProvider, ProviderUserInfo

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

def decode_apple_id_token(id_token: str, audience: str) -> dict[str, Any]:
    jwks_client = PyJWKClient(APPLE_JWKS_URL)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    decoded: dict[str, Any] = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=APPLE_ISSUER,
    )
    return decoded

def _name_from_apple_user_json(user_json: str) -> Optional[str]:
    parsed = json.loads(user_json)
    name_obj = parsed.get("name")
    if not isinstance(name_obj, dict):
        return None
    first = (name_obj.get("firstName") or "").strip()
    last = (name_obj.get("lastName") or "").strip()
    combined = f"{first} {last}".strip()
    return combined if combined else None

class AppleProvider(BaseAuthProvider):
    """Провайдер Sign in with Apple (OAuth 2.0, Services ID как client_id)."""

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.APPLE, config)
        if not self.auth_url:
            self.auth_url = DEFAULT_AUTH_URL
        if not self.token_url:
            self.token_url = DEFAULT_TOKEN_URL
        if not self.scope or self.scope == "openid profile email":
            self.scope = DEFAULT_SCOPE
        raw_key = config.apple_private_key or ""
        self._private_key_pem = _normalize_apple_pem(raw_key) if raw_key.strip() else ""
        self._team_id = config.apple_team_id or ""
        self._key_id = config.apple_key_id or ""

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
            _normalize_apple_pem(self.config.apple_private_key)
        except ValueError as e:
            logger.warning("apple_private_key некорректен: %s", e)
            return False
        if not self.auth_url or not self.token_url:
            logger.warning("auth_url или token_url не заданы для apple")
            return False
        return True

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
            "response_mode": "form_post",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> Tuple[str, Optional[str]]:
        client_secret = build_apple_client_secret(
            self._team_id,
            self.client_id or "",
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
        token_data = response.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise ValueError("Apple не вернул id_token")
        refresh_token = token_data.get("refresh_token")
        return id_token, refresh_token

    async def get_user_info(
        self,
        access_token: str,
        first_login_user_json: Optional[str] = None,
    ) -> ProviderUserInfo:
        claims = decode_apple_id_token(access_token, self.client_id or "")
        sub = claims.get("sub")
        if not sub:
            raise ValueError("Apple id_token без sub")

        email = claims.get("email")
        if isinstance(email, str):
            email = email.strip()
        else:
            email = ""

        name = ""
        if first_login_user_json:
            try:
                parsed_name = _name_from_apple_user_json(first_login_user_json)
                if parsed_name:
                    name = parsed_name
            except json.JSONDecodeError:
                logger.warning("Некорректный oauth_first_login_user_json от Apple")

        if not name and email:
            name = email.split("@")[0]
        if not name:
            name = str(sub)

        return ProviderUserInfo(
            provider_user_id=str(sub),
            email=email,
            name=name,
            avatar_url=None,
            raw_data=dict(claims),
        )
