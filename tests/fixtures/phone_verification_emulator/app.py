"""ASGI-приложение эмулятора провайдеров верификации телефона.

Протоколы — по официальной документации (см. CONTRACT.md):
- Telegram Bot API:   POST /tg/bot<token>/sendMessage
- MAX Bot API:        POST /max/messages?chat_id= (Authorization: <access_token>;
                      query access_token deprecated → 401)
- Yandex ID OAuth:    GET /yandex/authorize, POST /yandex/token, GET /yandex/info
- VK ID OAuth2/PKCE:  GET /vk/authorize, POST /vk/oauth2/auth, POST /vk/oauth2/user_info
- Sber ID OIDC:       GET /sber/CSAFront/oidc/authorize.do (nonce обязателен),
                      POST /sber/ru/prod/tokens/v2/oidc (rquid),
                      GET /sber/ru/prod/sberbankid/v2.1/userinfo (x-introspect-rquid)
- SMS.RU:             GET /smsru/sms/send
"""

from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from core.types import JsonObject, parse_json_object
from tests.fixtures.phone_verification_emulator.store import ProviderEmulatorStore


def _s256(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )


def create_phone_verification_emulator_app(store: ProviderEmulatorStore) -> FastAPI:
    app = FastAPI()
    now = int(time.time())

    # -- Telegram Bot API ---------------------------------------------------

    @app.post("/tg/bot{token}/sendMessage")
    async def tg_send_message(token: str, request: Request) -> JSONResponse:
        body = parse_json_object(await request.body(), "tg.sendMessage")
        store.telegram_messages.append(body)
        store._counter += 1
        mid = store._counter
        return JSONResponse(
            {
                "ok": True,
                "result": {
                    "message_id": mid,
                    "from": {"id": 1, "is_bot": True, "first_name": "EmuBot"},
                    "chat": {"id": body.get("chat_id"), "type": "private"},
                    "date": now,
                    "text": body.get("text", ""),
                },
            }
        )

    @app.post("/tg/bot{token}/getUpdates")
    async def tg_get_updates(token: str, request: Request) -> JSONResponse:
        _ = token
        body = parse_json_object(await request.body(), "tg.getUpdates")
        offset = int(str(body.get("offset") or 0))
        updates = [
            u
            for u in store.telegram_updates
            if int(str(u.get("update_id") or 0)) >= offset
        ]
        return JSONResponse({"ok": True, "result": updates})

    @app.post("/tg/bot{token}/deleteWebhook")
    async def tg_delete_webhook(token: str) -> JSONResponse:
        _ = token
        store.telegram_webhook_deleted += 1
        return JSONResponse({"ok": True, "result": True})

    # -- MAX Bot API ---------------------------------------------------------

    @app.post("/max/messages")
    async def max_send_message(request: Request) -> JSONResponse:
        params = dict(request.query_params)
        # Официальный контракт: токен в Authorization header;
        # query access_token deprecated и отклоняется (401).
        auth = request.headers.get("authorization") or ""
        store.max_authorization.append(auth)
        if "access_token" in params or auth != store.max_access_token:
            return JSONResponse(
                {"error": "unauthorized"}, status_code=401
            )
        body = parse_json_object(await request.body(), "max.messages")
        store.max_messages.append((params, body))
        return JSONResponse(
            {
                "message": {
                    "sender": {"user_id": 1, "first_name": "EmuMaxBot", "is_bot": True},
                    "recipient": {
                        "chat_id": int(str(params.get("chat_id") or "0")),
                        "chat_type": "dialog",
                        "user_id": None,
                    },
                    "timestamp": now * 1000,
                    "body": {
                        "mid": f"mid.{store._counter}",
                        "seq": store._counter,
                        "text": body.get("text", ""),
                        "attachments": [],
                    },
                }
            }
        )

    # -- OAuth2/OIDC ----------------------------------------------------------

    async def _authorize(provider: str, request: Request) -> Response:
        params = dict(request.query_params)
        store.authorize_requests.setdefault(provider, []).append(params)
        redirect_uri = params.get("redirect_uri") or ""
        state = params.get("state") or ""
        if params.get("response_type") != "code" or not redirect_uri:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        expected = store.client_credentials.get(provider)
        if expected is not None and params.get("client_id") != expected[0]:
            return RedirectResponse(f"{redirect_uri}?{urlencode({'error': 'unauthorized_client', 'state': state})}", status_code=302)
        allowed = store.allowed_scopes.get(provider)
        if allowed is not None:
            requested = set((params.get("scope") or "").split())
            if not requested or not requested.issubset(allowed):
                return RedirectResponse(f"{redirect_uri}?{urlencode({'error': 'invalid_scope', 'state': state})}", status_code=302)
        account = store.oauth_accounts.get(provider)
        if account is None:
            return RedirectResponse(f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}", status_code=302)
        code = store.next_id(f"oc_{provider}")
        # VK ID возвращает device_id в redirect — он обязателен при обмене кода.
        device_id = store.next_id("dev") if provider == "vk" else ""
        store.auth_codes[code] = (provider, state, str(params.get("code_challenge") or ""))
        query: dict[str, str] = {"code": code, "state": state}
        if device_id:
            query["device_id"] = device_id
        return RedirectResponse(f"{redirect_uri}?{urlencode(query)}", status_code=302)

    def _token_error(provider: str, request_data: dict[str, str], code: str) -> JSONResponse | None:
        if store.oauth_token_fail.get(provider):
            return JSONResponse({"error": "temporarily_unavailable"}, status_code=store.oauth_token_fail[provider])
        if request_data.get("grant_type") != "authorization_code":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        entry = store.auth_codes.get(code)
        if entry is None or entry[0] != provider:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        expected = store.client_credentials.get(provider)
        if expected is not None and (
            request_data.get("client_id") != expected[0]
            or request_data.get("client_secret") != expected[1]
        ):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        return None

    def _issue(provider: str, extra: JsonObject) -> JSONResponse:
        token = store.next_id(f"at_{provider}")
        store.access_tokens[token] = provider
        return JSONResponse(
            {
                "access_token": token,
                "refresh_token": store.next_id("rt"),
                "token_type": "bearer",
                "expires_in": 3600,
                **extra,
            }
        )

    async def _form(request: Request) -> dict[str, str]:
        raw = await request.form()
        return {str(k): str(v) for k, v in raw.items()}

    @app.get("/yandex/authorize")
    async def yandex_authorize(request: Request) -> Response:
        return await _authorize("yandex", request)

    @app.post("/yandex/token")
    async def yandex_token(request: Request) -> JSONResponse:
        data = await _form(request)
        store.token_requests.setdefault("yandex", []).append(data)
        err = _token_error("yandex", data, data.get("code") or "")
        if err is not None:
            return err
        return _issue("yandex", {"uid": 12345})

    @app.get("/yandex/info")
    async def yandex_info(request: Request) -> JSONResponse:
        auth = request.headers.get("authorization") or ""
        if not auth.startswith("OAuth ") or auth[6:] not in store.access_tokens:
            return JSONResponse({"error": "invalid_token"}, status_code=401)
        account = store.oauth_accounts["yandex"]
        phones = (
            [{"id": 1, "number": account.phone}] if account.phone else []
        )
        return JSONResponse(
            {
                "id": account.user_id,
                "login": "emu-user",
                "client_id": store.client_credentials["yandex"][0],
                "default_email": "emu@yandex.ru",
                "emails": ["emu@yandex.ru"],
                "real_name": f"{account.first_name} {account.last_name}",
                "first_name": account.first_name,
                "last_name": account.last_name,
                "sex": "male",
                "default_phone": {"id": 1, "number": account.phone} if account.phone else {},
                "phones": phones,
            }
        )

    @app.get("/vk/authorize")
    async def vk_authorize(request: Request) -> Response:
        return await _authorize("vk", request)

    @app.post("/vk/oauth2/auth")
    async def vk_token(request: Request) -> JSONResponse:
        data = await _form(request)
        store.token_requests.setdefault("vk", []).append(data)
        err = _token_error("vk", data, data.get("code") or "")
        if err is not None:
            return err
        # VK ID: обязательны device_id + state из authorize-redirect.
        entry = store.auth_codes[data.get("code") or ""]
        if not data.get("device_id") or data.get("state") != entry[1]:
            return JSONResponse({"error": "invalid_request", "error_description": "device_id/state"}, status_code=400)
        # VK ID требует PKCE: code_verifier обязан совпасть с code_challenge.
        challenge = entry[2]
        if not challenge or _s256(data.get("code_verifier") or "") != challenge:
            return JSONResponse({"error": "invalid_grant", "error_description": "code_verifier"}, status_code=400)
        account = store.oauth_accounts["vk"]
        return _issue("vk", {"id_token": "emu-id-token", "user_id": account.user_id, "scope": "phone"})

    @app.post("/vk/oauth2/user_info")
    async def vk_user_info(request: Request) -> JSONResponse:
        data = await _form(request)
        auth = request.headers.get("authorization") or ""
        token = data.get("access_token") or (auth[7:] if auth.startswith("Bearer ") else "")
        if token not in store.access_tokens:
            return JSONResponse({"error": "invalid_token"}, status_code=401)
        account = store.oauth_accounts["vk"]
        user: JsonObject = {
            "user_id": account.user_id,
            "first_name": account.first_name,
            "last_name": account.last_name,
            "avatar": "https://pp.userapi.com/emu.png",
            "sex": 2,
            "verified": False,
            "birthday": "01.01.2000",
        }
        if account.phone:
            user["phone"] = account.phone.lstrip("+")
        return JSONResponse({"user": user})

    @app.get("/sber/CSAFront/oidc/authorize.do")
    async def sber_authorize(request: Request) -> Response:
        # Официальный контракт: nonce обязателен в запросе кода авторизации.
        if not request.query_params.get("nonce"):
            return JSONResponse({"error": "invalid_request", "error_description": "nonce required"}, status_code=400)
        return await _authorize("sber", request)

    @app.post("/sber/ru/prod/tokens/v2/oidc")
    async def sber_token(request: Request) -> JSONResponse:
        # Заголовок rquid обязателен по контракту back-channel Сбер ID.
        if not request.headers.get("rquid"):
            return JSONResponse({"error": "invalid_request", "error_description": "rquid required"}, status_code=400)
        data = await _form(request)
        store.token_requests.setdefault("sber", []).append(data)
        err = _token_error("sber", data, data.get("code") or "")
        if err is not None:
            return err
        return _issue("sber", {"id_token": "emu-id-token"})

    @app.get("/sber/ru/prod/sberbankid/v2.1/userinfo")
    async def sber_userinfo(request: Request) -> JSONResponse:
        if not request.headers.get("x-introspect-rquid"):
            return JSONResponse({"error": "invalid_request", "error_description": "x-introspect-rquid required"}, status_code=400)
        auth = request.headers.get("authorization") or ""
        if not auth.startswith("Bearer ") or auth[7:] not in store.access_tokens:
            return JSONResponse({"error": "invalid_token"}, status_code=401)
        account = store.oauth_accounts["sber"]
        claims: JsonObject = {
            "sub": account.user_id,
            "iss": "https://id.sber.ru",
            "name": f"{account.first_name} {account.last_name}",
            "given_name": account.first_name,
            "family_name": account.last_name,
        }
        if account.phone:
            claims["phone_number"] = account.phone
            claims["phone_number_verified"] = True
        return JSONResponse(claims)

    # -- SMS.RU ----------------------------------------------------------------

    @app.get("/smsru/sms/send")
    async def smsru_send(request: Request) -> JSONResponse:
        params = dict(request.query_params)
        store.sms_requests.append(params)
        to = str(params.get("to") or "")
        if store.sms_top_status_code is not None:
            return JSONResponse(
                {
                    "status": "ERROR",
                    "status_code": store.sms_top_status_code,
                    "status_text": "emulated failure",
                }
            )
        inner_code = store.sms_inner_status_code or 100
        inner: JsonObject = {
            "status": "OK" if inner_code == 100 else "ERROR",
            "status_code": inner_code,
        }
        if inner_code == 100:
            inner["sms_id"] = store.next_id("emu-sms")
            # Расширение эмулятора: себестоимость для budget-учёта платформы.
            inner["cost"] = "0.40"
        else:
            inner["status_text"] = "emulated delivery failure"
        return JSONResponse(
            {
                "status": "OK",
                "status_code": 100,
                "sms": {to: inner},
                "balance": "4122.56",
            }
        )

    return app
