---
trigger: model_decision
description: "WebRTC звонки в Sync: архитектура, сигналинг, LiveKit SFU, гостевые ссылки"
globs:
---

# WebRTC Звонки (Sync)

## Тип звонка и клиент

- В API и БД один тип: **`call_type: "video"`**. Значение `audio` в старых клиентах (`call.invite`, `POST /calls/links`) нормализуется в `video` на сервере; миграция `sync_0008` приводит исторические строки в БД.
- Камера по умолчанию и при переключении: **`localStorage`** ключ `humanitec.sync.call.camera_enabled` (boolean-строка). После `enableCameraAndMicrophone()` SFU выставляет `setCameraEnabled` из LS; в P2P — `getVideoTracks().enabled`.
- Демонстрация экрана: `new Room({ publishDefaults: { screenShareEncoding: ScreenSharePresets.h1080fps30.encoding } })` — выше битрейт/кадры, чем дефолт SDK (`h1080fps15`). При старте шеринга камера **вымкнута** (`setCameraEnabled(false)`), состояние до шеринга хранится для восстановления; после остановки экрана (кнопка или системный «Stop sharing») камера возвращается. Пока идёт демонстрация, кнопка камеры **disabled**. В сетке при активном screen share у участника показывается **только** плитка экрана (`_videoPubsForGrid`). Кнопка экрана только при `getDisplayMedia`; класс плитки экрана — `screen`, `object-fit: contain`.
- Полный экран по плитке: кнопка на плитке с видео — в DOM **после** `<video>` и подписи, иначе видео перекрывает кнопку и выход из fullscreen только с клавиатуры. Выход: повторный клик (учитывается, что `document.fullscreenElement` иногда сам `<video>` внутри плитки, а не `.participant-tile` — проверка `tile.contains(fullscreenElement)`), **Escape** при фокусе на странице, синхронизация иконки через `fullscreenchange` и `data-tile-key` с `closest('.participant-tile')`; префиксы webkit / moz / ms; при завершении звонка — выход из fullscreen. **iOS Safari на телефоне:** полноэкранный API для произвольного `div` часто недоступен — используется **`video.webkitEnterFullscreen()`**, сброс активной кнопки по `webkitendfullscreen`. **Android (Chrome и др. Blink):** у `<video>` обычно **нет** `webkitEnterFullscreen` — срабатывает **`element.requestFullscreen()`** на плитке; разрешения камеры/микрофона — системный диалог при первом захвате (LiveKit `enableCameraAndMicrophone`), отдельного кода под Android не требуется. Оверлей: отступы **`env(safe-area-inset-*)`** на `:host` при `viewport-fit=cover` (вырезы, нижняя панель жестов). Сетка на узком экране: **column flex** вместо `place-items: center` у grid, чтобы плитки не наезжали друг на друга. Глобальный порядок слоя: `nextModalLayerZIndex()` и `--platform-modal-layer-z` на `:host` у `call-overlay` / `call-incoming` (как у платформенных модалок).

### Инкогнито и «пустая комната»

- **Пустой `localStorage`** (новое окно / инкогнито): не восстанавливается выбранный канал и прочие сохранённые настройки UI. Звонок из шапки без выбранного канала идёт в **отдельный** скрытый канал встречи — в комнате только вы, это не баг маршрутизации LiveKit.
- **Гостевая ссылка** `POST /calls/links` **без** привязки к текущему `call_id` (или первый заход по ссылке, пока в БД у записи `sync_call_links.call_id` ещё `NULL`): при первом `POST /calls/join/{token}` создаётся **отдельный** SFU-звонок и комната `link-{prefix}`, не та же, что у участников звонка из чата. Чтобы гость попал в **тот же** LiveKit room, что и чат, ссылка должна быть создана с **`call_id`** активного звонка (кнопка «Скопировать ссылку» в оверлее передаёт его).

### UI оверлея (устройства и качество звука, только SFU)

Готового виджета устройств у LiveKit нет — в [`call-overlay.js`](apps/sync/ui/features/call-overlay.js) своя панель: **слева** кнопка (шестерёнка) — микрофон, камера, динамик; **по центру** микрофон, камера, экран, сброс; **справа** «⋯» — пункт «Качество звука» с подменю (шумодав, эхоподавление, автогромкость). Десктоп: `.call-menu-flyout` слева от строки (`right: calc(100% + 8px)`). **Узкий экран:** flyout **под** пунктом (relative, колонка), иначе касания уходят под слой видео. Закрытие по касанию снаружи: `pointerdown`/`touchstart` на `document` в **bubble**; «внутри» не закрывать — `.call-menu` / `.call-menu-flyout`, вся `.controls-bar`, `.header`, `.settings-error` (иначе на iOS `requestUpdate` после touch ломает последующий `click` по центральным кнопкам). Тап по сетке видео закрывает меню. **iOS WebKit:** у `.participant-tile video` — `pointer-events: none`, у кнопки полноэкранного режима и подписи — `auto`; в нативном fullscreen плитки у видео снова `pointer-events: auto`. Шапка и `.controls-bar`: высокий `z-index`, `transform: translateZ(0)`, `-webkit-backdrop-filter` у панели — чтобы слой UI был над композитным слоем видео. Показывается только при активном SFU (`_sfuMediaUiAvailable()`); в P2P этих кнопок нет.

- Смена устройства: `navigator.mediaDevices.enumerateDevices()` + `room.switchActiveDevice('audioinput' | 'videoinput' | 'audiooutput', deviceId)`. Выбор динамика — только если в браузере есть `HTMLMediaElement.setSinkId` (иначе блок скрыт).
- Обработка звука: у публикации микрофона `LocalAudioTrack.restartTrack({ noiseSuppression, echoCancellation, autoGainControl })`. Сохранение в **localStorage**: `humanitec.sync.call.audio_noise_suppression`, `humanitec.sync.call.audio_echo_cancellation`, `humanitec.sync.call.audio_auto_gain` (строки `"true"` / `"false"`). После подключения перезапуск с этими флагами выполняется только если хотя бы один из ключей уже задан (иначе остаются дефолты захвата LiveKit/браузера).
- Ошибки смены устройств/перезапуска: строка `_mediaSettingsError` над панелью, без перехода в полноэкранную «Ошибка звонка».
- Атрибут `call-type="audio"`: при старте SFU камера выключается, в меню устройств скрыт выбор камеры; P2P — `getUserMedia` без видеодорожки. Текущий API чата нормализует `call_type` в `video` на сервере, но атрибут оставлен для совместимости.

## Архитектура

| Участников | Режим | Медиа-путь |
|---|---|---|
| 2 | P2P | Браузер ↔ Браузер (DTLS/SRTP напрямую) |
| 3+ | SFU | Браузер ↔ LiveKit ↔ Браузер |

Сервер **не участвует** в медиа-потоке при P2P. При SFU — только LiveKit.

В коде [`call_handlers.py`](apps/sync/realtime/call_handlers.py) сейчас **`P2P_MAX = 0`**: все звонки — **SFU**. **Speech-to-chat** (речь в ленту): канал **`speech_to_chat_enabled`**, серверный LiveKit segmented egress микрофона → S3 → `messages.send`; пустой `file_results` у egress — догрузка сегментов листингом S3 по префиксу `sync-speech/...` и курсору **`last_segment_s3_key`**. Длительность сегмента egress — **`calls.speech_to_chat.segment_seconds`** (по умолчанию 60 с; при смене очень больших значений сверять с лимитами вашей версии LiveKit Egress на стенде). После скачивания сегмента воркер: **`volumedetect`** — если **`max_volume` < `speech_segment_discard_below_max_volume_db`**, сообщение в канал не создаётся, курсор сегмента всё равно сдвигается; иначе **обрезка кромочной тишины** (`silenceremove` + `areverse` в [`core/files/audio_silence.py`](core/files/audio_silence.py)) с порогами **`speech_segment_trim_*`**; если после обрезки длительность < **`speech_segment_min_post_duration_ms`**, публикация тоже пропускается. Полное описание пайплайнов, locks и флагов — **[`sync.mdc`](.cursor/rules/sync.mdc)**; TTL lock авто-STT — **`transcribe_audio_redis_lock_ttl_seconds`** в [`BaseSettings`](core/config/base.py).

## Сигналинг

```
Мутации (call.invite/accept/decline/hangup):
  /sync/ws → TaskIQ (sync queue) → call_handlers.py → SyncCall БД
             → publish_realtime_events → Redis sync.realtime.events
             → PubSubFanout в ws.py → только сокеты (company_id, user_id) из recipient_user_ids
               (участники канала звонка; call.signal — один target_user_id)

P2P relay (call.signal):
  /sync/ws → ws.py (ПРЯМОЙ relay, без TaskIQ) → тот же Redis + fanout только на target_user_id
             Обход TaskIQ критичен для WebRTC latency!

Токен SFU:
  GET /sync/api/v1/calls/{call_id}/token → LiveKitClient.generate_token()
```

## WS Команды

| Тип | Через TaskIQ | Описание |
|---|---|---|
| `call.invite` | да | Создаёт звонок, уведомляет участников |
| `call.accept` | да | Участник принимает |
| `call.decline` | да | Участник отклоняет |
| `call.hangup` | да | Участник завершает |
| `call.signal` | **НЕТ** | P2P relay (offer/answer/ICE), прямой путь в ws.py |

## WS События (→ /sync/ws, изолировано по компании и каналу)

`call.incoming`, `call.accepted`, `call.declined`, `call.ended`, `call.signal`, `call.participant_joined`, `call.participant_left`

К телу `call.incoming` (после `CallRead`) сервер добавляет: `initiator_user_id`, `caller_display_name` (имя из `UserRepository`), `incoming_channel_kind` (`direct` / `group` / `topic`), для не-direct при непустом имени — `channel_display_name`. Клиент баннера: заголовок через `SyncStore.channelDisplayTitle` если канал уже в store, иначе подсказки с сервера.

В Redis публикуется `RealtimeEvent` с полями `company_id` и `recipient_user_ids` (маршрутизация); в WebSocket клиенту уходит только `{type, channel_id?, payload}` — без утечки списка получателей. Call-события уходят **только участникам канала** (не всей компании). Платформенные тосты `/ws/notifications` для call-событий не используются.

## REST API

```
GET  /sync/api/v1/calls/turn-credentials     → TurnCredentials (HMAC-SHA1, stateless)
POST /sync/api/v1/calls/links                → CallLinkRead (auth required, создаёт гостевую ссылку)
GET  /sync/api/v1/calls/{call_id}            → CallRead
GET  /sync/api/v1/calls/{call_id}/token      → {token, livekit_url} (только SFU)
GET  /sync/api/v1/calls/join/{token}         → CallLinkInfo (публично, без auth; `creator_avatar_url` при наличии аватара в профиле)
POST /sync/api/v1/calls/join/{token}         → JoinResponse (`participant_names`: identity → имя для оверлея у гостя)
```

## Гостевые ссылки

- Зарегистрированный → identity = `user_id`, cookie auth.
- Гость → body `{guest_name}` → identity = `guest:{uuid8}:{name}`.
- Всегда SFU режим (P2P для гостей не поддерживается).
- `POST /calls/links` с **`call_id`** (оверлей «Скопировать ссылку»): ссылка сразу привязана к текущему `SyncCall` — гость в той же LiveKit-комнате, что и чат (`call-{uuid}`), без отдельной `link-*`.
- Без `call_id`: первый вход по ссылке создаёт новый `SyncCall` и комнату `link-{tokenPrefix}`; последующие по той же ссылке переиспользуют.
- Публичный URL для календаря и UI: **`join_url`** в ответе API — `{platform_public_base_url}/l/{code}`; резолв на frontend (`GET /l/{code}`) → редирект на `/sync/join/{link_token}`. Хранение: `platform_short_links` (kind `sync_call_join`), `ShortLinkService` в `core/short_links/`; при удалении ссылки звонка — удаление short link по `link_token`.
- Страница: `/sync/join/{token}` → `call-join.html` (публичный маршрут в `main.py`).
- Route config: `/sync/api/v1/calls/join/*` → `auth_required=False`.

## core/calls/

| Файл | Содержимое |
|---|---|
| `models.py` | `TurnCredentials`, `CallMode`, `SignalType` |
| `livekit_client.py` | `LiveKitClient` — create_room, delete_room, generate_token, start/stop egress в S3; трейсируемые вызовы требуют **`company_id` и `user_id`** (платформенный журнал). `_api_url()` конвертирует `ws://` → `http://` для Twirp API |
| `turn.py` | `generate_turn_credentials()` — HMAC-SHA1, алгоритм coturn REST |

### CallOverlay SFU (переподключение)

После hangup `livekit-token` остаётся в атрибутах; в `updated()` без флага `_sfuSessionFinished` снова вызывался бы `_connectSFU()`. Флаг выставляют hangup, `RoomEvent.Disconnected`, `disconnectedCallback`. В `sync-app`: `call-ended` только снимает оверлей; `call-hangup-request` — одна отправка WS `call.hangup` (не дублировать с `call-ended`). Ack на `call.hangup` возвращает `CallRead` с `call_id` (как и `call.invite`); обработчик WS-ответов не должен снова вызывать `_openCallOverlay` для этого ack — иначе оверлей закрывается по `call-ended` и тут же открывается. Решение: помечать `id` исходящей команды `call.hangup` (`_callHangupRequestIds`) и при ack с этим `id` не открывать оверлей.

Видеосетка строится из `_tiles` (по публикациям камеры и screen share на участника). События `LocalTrackPublished` / `LocalTrackUnpublished` обновляют сетку.

## Конфигурация

```json
"calls": {
  "livekit_url": "ws://localhost:7880",
  "livekit_api_key": "devkey",
  "livekit_api_secret": "secret",
  "turn_host": "localhost",
  "turn_port": 3478,
  "turn_secret": "turnsecret",
  "turn_credential_ttl": 86400
}
```

Локально ключи: `devkey` / `secret`. В `docker-compose-dev.yaml` сервер поднимается с `LIVEKIT_CONFIG` (Redis `db: 2`) и сервисом `livekit-egress`, иначе API egress отдаёт 503.

## Инфраструктура

| Окружение | LiveKit порт | coturn |
|---|---|---|
| dev | 7880 (`livekit` + `livekit-egress` в compose) | host network |
| test | 7890 (ext) / 7880 (int) | нет |
| prod | 7880 | host network |

`make test` запускает `livekit-test`, `livekit-egress-test` и `livekit-cli-test` автоматически через `mk/test.mk`.

### Headless publisher в тестах

- Для egress E2E без браузера используется `livekit-cli-test` (`livekit/livekit-cli`) как headless участник комнаты.
- Команда для симуляции медиа-потока: `lk room join --url ws://livekit-test:7880 --api-key devkey --api-secret secret --identity <id> --publish-demo <room>`.
- Для контейнерного egress endpoint `localhost`/`127.0.0.1` в S3-конфиге нормализуется в `host.docker.internal`, иначе egress внутри контейнера не сможет достучаться до host MinIO.
- При custom S3 endpoint (`S3Upload.endpoint`) включать `S3Upload.force_path_style = true`, иначе egress может строить virtual-host URL вида `<bucket>.<endpoint>` и падать на DNS в MinIO/локальном окружении.
- В `docker-compose-dev.yaml`, `docker-compose-prod.yaml` и `docker-compose-test.yaml` для `livekit-egress` должен быть `session_limits.file_output_max_duration: 1h`, чтобы запись не длилась дольше часа даже без клиентского stop.
- Без опубликованного медиатрэка egress завершится с `Start signal not received`, файл в S3 не появится.

## БД (sync)

| Таблица | Описание |
|---|---|
| `sync_calls` | Звонки: mode (p2p/sfu), status (ringing/active/ended), livekit_room_name |
| `sync_call_participants` | Участники: status (invited/joined/declined/left) |
| `sync_call_links` | Гостевые ссылки: link_token, expires_at, call_type |
| `sync_call_recordings` | Записи звонков: status (requested/recording/uploaded/failed), provider_job_id, raw_file_id |

## Запись и канал как интерфейс STT

- WS-команды: `call.recording.start`, `call.recording.stop` (без `call.meeting.*`).
- `call.recording.start` запускает `RoomCompositeEgress` с `EncodedFileOutput.s3`.
- `call.recording.stop` останавливает egress по `provider_job_id`.
- `sync_finalize_recording_task`: ожидание готового egress — **`calls.finalize_recording_egress_wait_timeout_seconds`** и **`finalize_recording_egress_poll_interval_seconds`**; затем `file/video` в канал с `call_id`. Отдельных таблиц встреч/summary для sync нет. Если egress завершился с «Stop called before pipeline could start» (слишком короткая запись), пользователю показывается «Запись слишком короткая — файл не был создан».
- WS-события звонка: `call.recording.started|stopped|failed` и прочие события участников; событий `call.transcript.*`, `call.summary.*`, `call.export.crm.*` нет.
- REST: `GET /sync/api/v1/calls/{call_id}/recordings`; транскрипция через `POST .../messages/.../transcribe`, `.../transcribe-video`, `POST .../channels/{channel_id}/calls/{call_id}/transcribe` (см. `sync.mdc`).
- `sync_spaces`: `namespace` для CRM/RAG; колонок автоэкспорта транскрипта/summary нет.

## Ключевые файлы

- `core/calls/` — переиспользуемая библиотека
- `apps/sync/realtime/call_handlers.py` — бизнес-логика P2P/SFU
- `apps/sync/ws.py` — прямой relay `call.signal`
- `apps/sync/api/calls.py` — REST + публичные эндпоинты
- `apps/sync/ui/features/call-overlay.js` — WebRTC оверлей (P2P нативный + SFU через `@livekit/client`, бандл в `core/frontend/static/assets/js/livekit/`, `importmap` в `index.html` / `call-join.html`)
- `apps/sync/ui/features/call-incoming.js` — баннер входящего звонка
- `apps/sync/ui/features/call-join.js` — страница входа по ссылке
- `apps/sync/ui/call-join.html` — отдельный HTML (не SPA sync)
- `tests/sync/unit/test_turn_credentials.py` — HMAC математика
- `tests/sync/db/test_call_repository.py` — CRUD реальная БД
- `tests/sync/realtime/test_call_handlers.py` — execute_command с реальным Redis и LiveKit
- `tests/sync/api/test_calls_api.py` — HTTP API
