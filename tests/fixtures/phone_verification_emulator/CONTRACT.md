# Phone Verification Emulator — контракты

Локальный HTTP-эмулятор официальных протоколов провайдеров верификации
номера телефона. Прод-код ходит на него через endpoint-оверрайды
`customer_auth.brands.<apex>.*_url` — без моков и monkeypatch.

| Провайдер | Официальный источник | Эндпоинты эмулятора |
|---|---|---|
| Telegram Bot API | https://core.telegram.org/bots/api | `POST /tg/bot<token>/sendMessage` |
| MAX Bot API | https://dev.max.ru/docs-api | `POST /max/messages?chat_id&access_token` |
| Yandex ID | https://yandex.ru/dev/id/doc | `GET /yandex/authorize`, `POST /yandex/token`, `GET /yandex/info` |
| VK ID | https://id.vk.ru/about/business/go/docs | `GET /vk/authorize`, `POST /vk/oauth2/auth`, `POST /vk/oauth2/user_info` |
| Sber ID OIDC | https://developers.sber.ru | `GET /sber/CSAFront/oidc/authorize.do` (обяз. `nonce`, `client_type`), `POST /sber/ru/prod/tokens/v2/oidc` (обяз. `rquid`), `GET /sber/ru/prod/sberbankid/v2.1/userinfo` (обяз. `x-introspect-rquid`) |
| SMS.RU | https://sms.ru/api/send | `GET /smsru/sms/send` |

## Ответы

- Telegram: `{"ok": true, "result": {message_id, from, chat, date, text}}`.
- MAX: `{"message": {sender, recipient, timestamp, body:{mid, seq, text, attachments}}}`.
- OAuth authorize → `302 redirect_uri?code&state` (`error=access_denied`, если
  аккаунт не засеян). Token → `access_token`+`refresh_token`+`token_type`+`expires_in`;
  ошибки — `{"error": ...}` по RFC 6749; VK проверяет `code_verifier` (PKCE S256).
- userinfo: Yandex — `Authorization: OAuth` + `default_phone.number`; VK —
  POST-форма `access_token` + `user.phone`; Sber — `Authorization: Bearer` +
  OIDC-claim `phone_number`.
- SMS.RU: `{"status":"OK","status_code":100,"sms":{"<to>":{...}},"balance":"..."}`.
  Расширение эмулятора: внутренний `sms.<to>.cost` (руб.) — для проверки
  учёта дневного бюджета платформы.

## Флаги отказов (store)

- `sms_inner_status_code` — `sms.<to>.status_code` (207 — недоставляемо и т.п.).
- `sms_top_status_code` — верхний `status_code != 100` (отказ провайдера).
- `oauth_token_fail[provider]` — HTTP-код на token endpoint (retryable-каскада).
- `oauth_accounts[provider]` — аккаунт пользователя; `phone=None` → userinfo без
  телефона (сценарий «у аккаунта нет верифицированного номера»).
