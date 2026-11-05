"""CustomerAuthService — сценарии подтверждения телефона покупателя.

Жизненный цикл `PhoneChallenge` (Redis, TTL `challenge_ttl_seconds`):
`start` → `choose` (код уходит отправителем из каскада) → `verify` / webhook /
OAuth callback → `confirmed` → выпуск customer-сессии.

Фолбек-каскада только по определённым состояниям провайдера: retryable
`ProviderError` при `send` перепадает на следующий отправитель; принятая
к отправке доставка не триггерит повторные отправки (правило customers.mdc).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time

from core.clients.phone_verification.base import CodeSender, ContactShareVerifier
from core.clients.phone_verification.registry import PhoneVerificationRegistry
from core.clients.phone_verification.telegram_bot import TelegramContactProvider
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.models import CustomerAuthConfig
from core.customers.challenge import ContactShareState, PhoneChallenge
from core.customers.contracts import (
    AuthStartView,
    AuthStatusView,
    CustomerMe,
    DirectVerificationRequest,
    MethodChallengedView,
    MethodOption,
    ProviderPhone,
    now_ts,
)
from core.customers.enums import (
    ClientKind,
    CustomerIdentityProvider,
    DirectAuthorizationKind,
    PhoneChallengeKind,
    PhoneChallengeStatus,
    PhoneVerificationErrorCode,
    PhoneVerificationMethod,
    provider_method,
)
from core.customers.errors import CustomerAuthError, ProviderError
from core.customers.models import Customer
from core.customers.phone import mask_phone, normalize_phone_e164
from core.customers.selection import (
    available_code_senders,
    select_methods_by_priority_asc,
)
from core.customers.service import CustomerService
from core.customers.session import CustomerSessionService
from core.logging import get_logger
from core.tracing.operation_span import traced_operation
from core.types import JsonObject

logger = get_logger(__name__)

_RL = "cust_auth:rl:"
_BUDGET = "cust_auth:budget:"
_CONTACT_USER = "cust_auth:contact_user:"
_TG_POLL_LOCK = "cust_auth:tg_poll:lock"
_TG_POLL_OFFSET = "cust_auth:tg_poll:offset:"
_TG_POLL_LOCK_TTL_S = 120
_TG_POLL_OFFSET_TTL_S = 7 * 86400
_TG_POLL_BUDGET_S = 55.0
_TG_POLL_REQUEST_TIMEOUT_S = 25


def _code_pepper() -> str:
    secret_key = get_settings().auth.jwt_secret_key
    if not secret_key:
        raise ValueError("JWT secret key is not configured (auth.jwt_secret_key)")
    return secret_key


def _hash_code(code: str, challenge_id: str) -> str:
    return hashlib.sha256(
        f"{code}|{challenge_id}|{_code_pepper()}".encode()
    ).hexdigest()


def _gen_code(length: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


class CustomerAuthService:
    """Оркестратор customer-auth (код + direct + OAuth + эмулятор)."""

    def __init__(
        self,
        *,
        cfg: CustomerAuthConfig,
        env: str,
        redis: RedisClient,
        customers: CustomerService,
        sessions: CustomerSessionService,
    ) -> None:
        self._cfg: CustomerAuthConfig = cfg
        self._env: str = env
        self._redis: RedisClient = redis
        self._customers: CustomerService = customers
        self._sessions: CustomerSessionService = sessions

    def _registry(self, apex: str) -> PhoneVerificationRegistry:
        return PhoneVerificationRegistry.build(self._cfg, apex, env=self._env)

    def registry_for(self, apex: str) -> PhoneVerificationRegistry:
        """Реестр провайдеров для бренда — для protocol handlers (webhook)."""
        return self._registry(apex)

    # -- rate limits / бюджет ---------------------------------------------

    async def _rate_limit(self, name: str, key: str, limit: int, ttl: int) -> None:
        counter = f"{_RL}{name}:{key}"
        count = await self._redis.eval(
            "local n = redis.call('INCR', KEYS[1]) if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end return n",
            1,
            counter,
            str(ttl),
        )
        if isinstance(count, int) and count > limit:
            raise CustomerAuthError(PhoneVerificationErrorCode.RATE_LIMITED)

    async def _check_limits(self, phone: str | None, ip: str) -> None:
        limits = self._cfg.limits
        if phone:
            await self._rate_limit("start_phone", phone, limits.starts_per_phone_hour, 3600)
        if ip:
            await self._rate_limit("start_ip", ip, limits.starts_per_ip_hour, 3600)

    async def _check_send_limits(self, phone: str, ip: str) -> None:
        limits = self._cfg.limits
        await self._rate_limit("send_phone", phone, limits.sends_per_phone_day, 86400)
        if ip:
            await self._rate_limit("send_ip", ip, limits.sends_per_ip_day, 86400)

    async def _spend_budget(self, cost_rub: float) -> None:
        """Дневной бюджет платформы на платные каналы (SMS-фолбек)."""
        day = time.strftime("%Y%m%d", time.gmtime())
        key = f"{_BUDGET}{day}"
        kopecks = int(cost_rub * 100)
        spent = await self._redis.eval(
            "local n = redis.call('INCRBY', KEYS[1], ARGV[1]) if tonumber(n) == tonumber(ARGV[1]) then redis.call('EXPIRE', KEYS[1], 90000) end return n",
            1,
            key,
            str(kopecks),
        )
        if isinstance(spent, int) and spent > self._cfg.daily_budget_rub * 100:
            logger.warning("customer_auth.budget_exceeded", day=day, spent=spent)

    async def _budget_remaining(self) -> int:
        day = time.strftime("%Y%m%d", time.gmtime())
        raw = await self._redis.get(f"{_BUDGET}{day}")
        spent = int(raw) if raw else 0
        return self._cfg.daily_budget_rub * 100 - spent

    # -- start / choose ----------------------------------------------------

    async def start(
        self,
        *,
        company_id: str,
        phone: str | None,
        client: ClientKind,
        ip: str,
        apex: str,
    ) -> AuthStartView:
        """Создать challenge и отдать список методов подтверждения."""
        phone_e164: str | None = None
        if phone:
            phone_e164 = normalize_phone_e164(phone)
            if phone_e164 is None:
                raise CustomerAuthError(PhoneVerificationErrorCode.INVALID_PHONE)
        await self._check_limits(phone_e164, ip)
        registry = self._registry(apex)
        methods = select_methods_by_priority_asc(self._cfg, registry, client=client)
        challenge = PhoneChallenge(
            scope_company_id=company_id,
            phone_e164=phone_e164 or "",
            client=client,
            selected_methods=[option.kind for option in methods],
            provider_data={"apex": apex},
        )
        await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
        return AuthStartView(
            challenge_id=challenge.challenge_id,
            phone_masked=mask_phone(phone_e164) if phone_e164 else None,
            methods=methods,
        )

    async def _send_code(
        self,
        challenge: PhoneChallenge,
        senders: list[CodeSender],
    ) -> CodeSender:
        """Каскада отправителей: реальные → эмулятор; SMS тратит бюджет платформы."""
        code = _gen_code(self._cfg.code_length)
        challenge.code_hash = _hash_code(code, challenge.challenge_id)
        last_error: ProviderError | None = None
        for sender in senders:
            try:
                if sender.provider == CustomerIdentityProvider.PHONE:
                    if await self._budget_remaining() <= 0:
                        raise ProviderError(
                            PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                            "daily budget exhausted",
                        )
                    async with traced_operation(
                        "customers.auth.send_code",
                        billing_usage_type="customer_auth_sms",
                        billing_resource_name=sender.provider.value,
                        billing_quantity=1,
                        billing_cost_origin="platform",
                    ):
                        delivery = await sender.send(challenge.phone_e164, code=code)
                    if delivery.price:
                        await self._spend_budget(delivery.price)
                else:
                    delivery = await sender.send(challenge.phone_e164, code=code)
                challenge.channel = delivery.channel
                challenge.provider_data["sender"] = sender.provider.value
                if delivery.provider_message_id:
                    challenge.provider_data["provider_message_id"] = (
                        delivery.provider_message_id
                    )
                return sender
            except ProviderError as exc:
                last_error = exc
                logger.warning(
                    "customer_auth.send_failed",
                    sender=sender.provider.value,
                    code=exc.code.value,
                    detail=exc.detail,
                )
                if not exc.retryable:
                    raise
                continue
        if last_error is not None:
            raise last_error
        raise CustomerAuthError(PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE)

    def _check_scope(self, challenge: PhoneChallenge, company_id: str) -> None:
        if challenge.scope_company_id != company_id:
            raise CustomerAuthError(PhoneVerificationErrorCode.FORBIDDEN_SCOPE)

    async def choose(
        self,
        *,
        challenge_id: str,
        method: PhoneVerificationMethod,
        company_id: str,
        ip: str,
        apex: str,
        return_url: str | None = None,
        callback_base: str = "",
    ) -> MethodChallengedView:
        """Выбор способа: отправка кода, contact link или OAuth URL."""
        challenge = await self._require_pending(challenge_id)
        self._check_scope(challenge, company_id)
        registry = self._registry(apex)

        if method == PhoneVerificationMethod.SMS_CODE:
            senders = available_code_senders(registry)
            if not senders or not self._cfg.sms_fallback_enabled:
                raise CustomerAuthError(PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE)
            await self._check_send_limits(challenge.phone_e164, ip)
            challenge.kind = PhoneChallengeKind.CODE
            challenge.method = method
            _ = await self._send_code(challenge, senders)
            challenge.resend_after_ts = now_ts() + self._cfg.resend_cooldown_seconds
            await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
            return MethodChallengedView(
                status="challenge_sent",
                challenge_id=challenge.challenge_id,
                kind=PhoneChallengeKind.CODE,
                method=method,
                channel=challenge.channel,
                expires_in=self._cfg.code_ttl_seconds,
                resend_after=self._cfg.resend_cooldown_seconds,
            )

        contact_share = registry.contact_share.get(method)
        if contact_share is not None:
            if not contact_share.available():
                raise CustomerAuthError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
            token = secrets.token_urlsafe(16)
            challenge.kind = PhoneChallengeKind.DIRECT
            challenge.method = method
            challenge.direct_kind = DirectAuthorizationKind.CONTACT_SHARE
            challenge.contact_share = ContactShareState(
                bot_link=contact_share.contact_link(token), token=token
            )
            if return_url:
                challenge.provider_data["return_url"] = return_url
            await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
            _ = await self._redis.set(
                f"{_CONTACT_USER}{challenge.contact_share.token}",
                challenge.challenge_id,
                ttl=self._cfg.challenge_ttl_seconds,
            )
            return MethodChallengedView(
                status="awaiting_contact",
                challenge_id=challenge.challenge_id,
                kind=PhoneChallengeKind.DIRECT,
                method=method,
                expires_in=self._cfg.challenge_ttl_seconds,
                deep_link=challenge.contact_share.bot_link,
            )

        oauth = registry.oauth.get(method)
        if oauth is not None:
            if not oauth.available():
                raise CustomerAuthError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
            state = secrets.token_urlsafe(24)
            # PKCE (RFC 7636): VK ID требует code_verifier при обмене кода.
            verifier = secrets.token_urlsafe(48)
            code_challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            challenge.kind = PhoneChallengeKind.DIRECT
            challenge.method = method
            challenge.direct_kind = DirectAuthorizationKind.OAUTH
            challenge.oauth_state = state
            challenge.provider_data["callback_base"] = callback_base
            challenge.provider_data["pkce_verifier"] = verifier
            if return_url:
                challenge.provider_data["return_url"] = return_url
            await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
            _ = await self._redis.set(
                oauth_state_index_key(state),
                challenge.challenge_id,
                ttl=self._cfg.challenge_ttl_seconds,
            )
            return MethodChallengedView(
                status="awaiting_oauth",
                challenge_id=challenge.challenge_id,
                kind=PhoneChallengeKind.DIRECT,
                method=method,
                expires_in=self._cfg.challenge_ttl_seconds,
                oauth_url=oauth.authorization_url(
                    state=state,
                    redirect_uri=self.oauth_redirect_uri(apex, method, callback_base),
                    code_challenge=code_challenge,
                ),
            )

        for verifier in registry.direct_verifiers:
            if verifier.method != method or not verifier.available():
                continue
            challenge.kind = PhoneChallengeKind.DIRECT
            challenge.method = method
            challenge.direct_kind = verifier.direct_kind
            if return_url:
                challenge.provider_data["return_url"] = return_url
            await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
            return MethodChallengedView(
                status="awaiting_contact",
                challenge_id=challenge.challenge_id,
                kind=PhoneChallengeKind.DIRECT,
                method=method,
                expires_in=self._cfg.challenge_ttl_seconds,
            )

        raise CustomerAuthError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)

    def oauth_redirect_uri(
        self, apex: str, method: PhoneVerificationMethod, callback_base: str
    ) -> str:
        """Публичный callback OAuth: `callback_base` — mount-префикс роутера."""
        provider = PhoneVerificationMethod(method).value.removesuffix("_id")
        return f"https://{apex}{callback_base}/oauth/{provider}/callback"

    # -- verify / confirm ---------------------------------------------------

    async def _require_pending(self, challenge_id: str) -> PhoneChallenge:
        challenge = await PhoneChallenge.load(self._redis, challenge_id)
        if challenge is None:
            raise CustomerAuthError(PhoneVerificationErrorCode.CHALLENGE_EXPIRED)
        if challenge.status != PhoneChallengeStatus.PENDING:
            raise CustomerAuthError(PhoneVerificationErrorCode.CHALLENGE_EXPIRED)
        return challenge

    async def _confirm(
        self,
        challenge: PhoneChallenge,
        *,
        provider: CustomerIdentityProvider,
        provider_user_id: str,
        phone_e164: str,
    ) -> tuple[Customer, str]:
        """Финал подтверждения: customer + identity + challenge.confirmed + JWT."""
        customer = await self._customers.get_or_create_by_phone(phone_e164)
        method = challenge.method or provider_method(provider)
        _ = await self._customers.link_identity(
            customer.customer_id,
            provider=provider,
            provider_user_id=provider_user_id,
            verified_phone_e164=phone_e164,
            verification_method=method,
            scope_company_id=challenge.scope_company_id,
        )
        challenge.status = PhoneChallengeStatus.CONFIRMED
        challenge.confirmed_customer_id = customer.customer_id
        await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
        await Customer.touch_login(customer.customer_id)
        token = self._sessions.issue(
            customer_id=customer.customer_id,
            phone_e164=customer.phone_e164,
            scope_company_id=challenge.scope_company_id,
            ttl_seconds=self._sessions.token_ttl(),
        )
        return customer, token

    async def verify_code(
        self, *, challenge_id: str, code: str, company_id: str
    ) -> tuple[Customer, str]:
        """Проверка короткого кода: попытки ограничены `attempts_per_challenge`."""
        challenge = await self._require_pending(challenge_id)
        self._check_scope(challenge, company_id)
        if challenge.kind != PhoneChallengeKind.CODE or not challenge.code_hash:
            raise CustomerAuthError(PhoneVerificationErrorCode.CODE_INVALID)
        if challenge.attempts_left <= 0:
            challenge.status = PhoneChallengeStatus.FAILED
            await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
            raise CustomerAuthError(PhoneVerificationErrorCode.ATTEMPTS_EXCEEDED)
        if _hash_code(code.strip(), challenge_id) != challenge.code_hash:
            challenge.attempts_left -= 1
            await challenge.save(self._redis, ttl=self._cfg.challenge_ttl_seconds)
            if challenge.attempts_left <= 0:
                raise CustomerAuthError(PhoneVerificationErrorCode.ATTEMPTS_EXCEEDED)
            raise CustomerAuthError(PhoneVerificationErrorCode.CODE_INVALID)
        sender_provider = CustomerIdentityProvider(
            challenge.provider_data.get("sender") or CustomerIdentityProvider.PHONE.value
        )
        return await self._confirm(
            challenge,
            provider=sender_provider,
            provider_user_id=f"phone:{challenge.phone_e164}",
            phone_e164=challenge.phone_e164,
        )

    async def verify_direct(
        self,
        *,
        challenge_id: str,
        proof: DirectVerificationRequest,
        company_id: str,
    ) -> tuple[Customer, str]:
        """Direct-подтверждение, присланное клиентом (эмулятор / mini-app)."""
        challenge = await self._require_pending(challenge_id)
        self._check_scope(challenge, company_id)
        registry = self._registry(self._apex_of(challenge))
        verifier = registry.direct_for(proof.provider)
        if verifier is None or not verifier.available():
            raise CustomerAuthError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        phones = await verifier.fetch_phones(proof)
        return await self._confirm_matched(
            challenge, phones=phones, provider=verifier.provider,
            provider_user_id=proof.provider_user_id or proof.contact_user_id or "",
        )

    async def _confirm_matched(
        self,
        challenge: PhoneChallenge,
        *,
        phones: list[ProviderPhone],
        provider: CustomerIdentityProvider,
        provider_user_id: str,
    ) -> tuple[Customer, str]:
        """Номер провайдера обязан совпасть с номером challenge."""
        matched = [p for p in phones if p.verified]
        phone = next(
            (p.phone_e164 for p in matched if p.phone_e164 == challenge.phone_e164),
            None,
        )
        if phone is None and challenge.phone_e164 and matched:
            raise CustomerAuthError(
                PhoneVerificationErrorCode.PROVIDER_MISMATCH,
                "provider phone != challenge phone",
            )
        phone = phone or (matched[0].phone_e164 if matched else challenge.phone_e164)
        if not provider_user_id:
            provider_user_id = f"{provider.value}:{phone}"
        return await self._confirm(
            challenge,
            provider=provider,
            provider_user_id=provider_user_id,
            phone_e164=phone,
        )

    def _apex_of(self, challenge: PhoneChallenge) -> str:
        apex = challenge.provider_data.get("apex")
        if apex:
            return apex
        return get_settings().primary_platform_domain

    # -- webhook / OAuth / polling ------------------------------------------

    async def handle_contact_update(
        self,
        *,
        provider: ContactShareVerifier,
        payload: JsonObject,
    ) -> None:
        """Webhook бота контактов (TG/MAX): `/start` → кнопка, `contact` → verify."""
        start = provider.parse_start(payload)
        if start is not None:
            chat_id, token = start
            challenge_id = await self._redis.get(f"{_CONTACT_USER}{token}")
            if challenge_id is None:
                return
            challenge = await PhoneChallenge.load(self._redis, challenge_id)
            if challenge is None or challenge.status != PhoneChallengeStatus.PENDING:
                return
            await provider.send_contact_request(chat_id)
            _ = await self._redis.set(
                f"{_CONTACT_USER}uid:{chat_id}", challenge_id,
                ttl=self._cfg.challenge_ttl_seconds,
            )
            return
        proof = provider.parse_update(payload)
        if proof is None or not proof.provider_user_id:
            return
        challenge_id = await self._redis.get(f"{_CONTACT_USER}uid:{proof.provider_user_id}")
        if challenge_id is None:
            return
        challenge = await self._require_pending(challenge_id)
        phones = await provider.fetch_phones(proof)
        _ = await self._confirm_matched(
            challenge, phones=phones, provider=provider.provider,
            provider_user_id=proof.provider_user_id,
        )

    async def poll_telegram_updates(
        self, *, budget_seconds: float = _TG_POLL_BUDGET_S
    ) -> int:
        """Цикл `getUpdates` по брендам с `telegram.polling_enabled`.

        Хост без входящего соединения от api.telegram.org не получает webhook —
        контракт тот же, что `handle_contact_update`, транспорт long-poll:
        offset живёт в Redis, активный экземпляр один на кластер (SET NX lock).
        `budget_seconds` ограничивает длину цикла — тик задачи должен укладываться
        между cron-вызовами. Возвращает число обработанных updates.
        """
        brands = [
            apex
            for apex, brand in self._cfg.brands.items()
            if brand.telegram is not None
            and brand.telegram.enabled
            and brand.telegram.polling_enabled
        ]
        if not brands:
            return 0
        providers: dict[str, TelegramContactProvider] = {}
        for apex in brands:
            verifier = self._registry(apex).contact_share.get(
                PhoneVerificationMethod.TELEGRAM_CONTACT
            )
            if isinstance(verifier, TelegramContactProvider) and verifier.available():
                providers[apex] = verifier
        if not providers or not await self._redis.set_nx(
            _TG_POLL_LOCK, "1", _TG_POLL_LOCK_TTL_S
        ):
            return 0
        try:
            # getUpdates при активном webhook отвечает 409 Conflict — снимаем его.
            for provider in providers.values():
                await provider.delete_webhook()
            processed = 0
            deadline = time.monotonic() + budget_seconds
            while time.monotonic() < deadline:
                for apex, provider in providers.items():
                    processed += await self._poll_telegram_brand(apex, provider)
            return processed
        finally:
            _ = await self._redis.delete(_TG_POLL_LOCK)

    async def _poll_telegram_brand(
        self, apex: str, provider: TelegramContactProvider
    ) -> int:
        """Один getUpdates-запрос по бренду + разбор updates."""
        offset_key = f"{_TG_POLL_OFFSET}{apex}"
        raw_offset = await self._redis.get(offset_key)
        offset = int(raw_offset) if raw_offset else 0
        updates = await provider.get_updates(offset, _TG_POLL_REQUEST_TIMEOUT_S)
        if not updates:
            return 0
        next_offset = offset
        for update in updates:
            raw_id = update.get("update_id")
            update_id = int(raw_id) if isinstance(raw_id, (int, str)) else 0
            if update_id >= next_offset:
                next_offset = update_id + 1
            await self.handle_contact_update(provider=provider, payload=update)
            # offset инкрементально: падение update не переобрабатывает предыдущие.
            _ = await self._redis.set(
                offset_key, str(next_offset), ttl=_TG_POLL_OFFSET_TTL_S
            )
        return len(updates)

    async def complete_oauth(
        self,
        *,
        method: PhoneVerificationMethod,
        code: str,
        state: str,
        apex: str,
        device_id: str = "",
    ) -> tuple[Customer, str, str | None]:
        """OAuth callback: state → challenge, code → phones, confirm → token + return_url."""
        registry = self._registry(apex)
        verifier = registry.oauth.get(method)
        if verifier is None or not verifier.available():
            raise CustomerAuthError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        challenge_id = await self._redis.get(oauth_state_index_key(state))
        if challenge_id is None:
            raise CustomerAuthError(PhoneVerificationErrorCode.CHALLENGE_EXPIRED)
        challenge = await self._require_pending(challenge_id)
        callback_base = str(challenge.provider_data.get("callback_base") or "")
        proof = DirectVerificationRequest(
            kind=DirectAuthorizationKind.OAUTH,
            provider=verifier.provider,
            oauth_code=code,
            oauth_state=state,
            oauth_code_verifier=challenge.provider_data.get("pkce_verifier"),
            oauth_device_id=device_id or None,
            redirect_uri=self.oauth_redirect_uri(apex, method, callback_base),
        )
        phones = await verifier.fetch_phones(proof)
        customer, token = await self._confirm_matched(
            challenge, phones=phones, provider=verifier.provider,
            provider_user_id=phones[0].phone_e164 if phones else "",
        )
        return customer, token, challenge.provider_data.get("return_url")

    async def status(
        self, challenge_id: str, *, company_id: str
    ) -> tuple[AuthStatusView, str | None]:
        """Polling: статус +, если confirmed, свежая сессия для Set-Cookie."""
        challenge = await PhoneChallenge.load(self._redis, challenge_id)
        if challenge is None:
            return (
                AuthStatusView(
                    status=PhoneChallengeStatus.EXPIRED, challenge_id=challenge_id
                ),
                None,
            )
        self._check_scope(challenge, company_id)
        token: str | None = None
        customer_view = None
        if (
            challenge.status == PhoneChallengeStatus.CONFIRMED
            and challenge.confirmed_customer_id
        ):
            customer = await self._customers.get(challenge.confirmed_customer_id)
            if customer is not None:
                customer_view = CustomerMe(
                    customer_id=customer.customer_id,
                    phone_e164=customer.phone_e164,
                    scope_company_id=challenge.scope_company_id,
                    name=customer.name,
                )
                token = self._sessions.issue(
                    customer_id=customer.customer_id,
                    phone_e164=customer.phone_e164,
                    scope_company_id=challenge.scope_company_id,
                    ttl_seconds=self._sessions.token_ttl(),
                )
        return (
            AuthStatusView(
                status=challenge.status,
                challenge_id=challenge.challenge_id,
                method=challenge.method,
                customer=customer_view,
            ),
            token,
        )

    def method_options(self, *, apex: str, client: ClientKind) -> list[MethodOption]:
        return select_methods_by_priority_asc(self._cfg, self._registry(apex), client=client)


def oauth_state_index_key(state: str) -> str:
    return f"{_CONTACT_USER}oauth:{state}"


__all__ = ["CustomerAuthService", "oauth_state_index_key"]
