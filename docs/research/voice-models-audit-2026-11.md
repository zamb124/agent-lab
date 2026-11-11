# Аудит речевых моделей платформы — ноябрь 2026

Дата аудита: 2026-11-11. Статус: исследование (без изменений кода).
Скоуп: ASR / TTS / VAD стек `apps/voice` + `apps/provider_litserve`. Фокус — русская речь, английский — вторично.
Ограничения отбора: только коммерчески чистые лицензии (Apache-2.0/MIT/BSD и эквивалент); self-hosted должен влезать в продакшен-GPU shared с embedding/rerank; облако — эталон качества и fallback.

**Замер 2026-11-11 (nvidia-smi в поде provider-litserve):** GPU — **RTX A4000 16GB** (16376 MiB, не A2000 6GB). Фактическое потребление: embedder + reranker = **2785 MiB**, +VAD ≈ **3038 MiB**, +GigaAM-v3 ≈ **4230 MiB**; Silero TTS и GigaAM — на `cuda:0`. **Свободно ~12 GB → VRAM не является ограничением**: Qwen3-TTS-1.7B и любой кандидат из отчёта влезает с запасом.

---

## 1. TL;DR — устарели ли наши модели?

| Компонент | Сейчас | Вердикт | Одной строкой |
|---|---|---|---|
| STT | GigaAM-v3 `e2e_rnnt` | ✅ **Актуально** — open SOTA для RU | Менять не нужно; стоит дооценить `v3_rnnt` и GigaAM-Multilingual-600M как записи каталога, и добавить стриминг-слой (T-One / sherpa-onnx) для partial-транскриптов |
| TTS | Silero `v5_5_ru` | ⚠️ **Устарело + лицензионный риск** | Бандл не последний (есть `v5_6_ru`), но главное — вся линейка `v5_*_ru` под **CC BY-NC** (некоммерческая). По качеству проигрывает Qwen3-TTS-1.7B (open, Apache-2.0) и облачным лидерам |
| VAD | silero-vad 6.2.3 | ✅ **Актуально** — последняя версия, MIT | Менять не нужно. Опционально — слой semantic turn-detection (smart-turn-v3) поверх VAD для endpointing |

**Главный вывод**: речевой стек устарел не по STT/VAD (там мы на SOTA), а по TTS — и по двум осям сразу: качество синтеза (Silero заметно «роботичнее» современных LM-based TTS) и лицензия (CC BY-NC запрещает коммерческое использование без договора с Silero).

---

## 2. Текущий стек (инвентарь по коду)

| Компонент | Модель | Источник | Ресурс |
|---|---|---|---|
| STT local | `ai-sage/GigaAM-v3`, revision `e2e_rnnt` (api id `gigaam-v3-rnnt-ru`) | `core/config/models.py` `ProviderLitserveInfraConfig.stt_models` | ~1 Gi VRAM (fp32), ~3 Gi весов на диске |
| STT cloud | `openai/whisper-large-v3` (cloud.ru); `yandex`, `sber` — stub-клиенты | `core/clients/speech_provider_catalog.py` | — |
| TTS local | Silero `v5_5_ru`, голос `xenia`, 24 kHz; allowlist `v5_ru`…`v5_5_ru` | `core/config/models.py`, `apps/provider_litserve/tts/engines.py` | ~150 Mi |
| TTS cloud | `openai/tts-1`, `openai/tts-1-hd` (cloud.ru); голоса Yandex/Sber в allowlist (stub) | `core/clients/speech_provider_catalog.py` | — |
| VAD | `silero-vad==6.2.3` (PyPI, Sep 2026 — последняя) | `pyproject.toml`, `apps/provider_litserve/vad/engines.py` | ~50 Mi |
| Пайплайн | Стриминг-STT = буферизация + VAD-сегментация, **native partial-транскриптов нет**; TTS — батч по сегментам ≤900 симв. | `core/clients/stt_streaming.py`, `apps/voice/workers/stt_worker.py` | — |

Инфра: `provider_litserve` на master-ноде, `nvidia.com/gpu: 1`, **RTX A4000 16GB** (замерено `nvidia-smi` 2026-11-11; комментарий «A2000 6GB» в `values.yaml` устарел — исправить). Shared с `Qwen3-Embedding-0.6B` (bf16) и `Qwen3-Reranker-0.6B` (fp16). STT также используется батчево: `core/files/media/chunked_stt.py` (файлы/сообщения sync).

### VRAM-бюджет — фактический замер (2026-11-11, прод)

| Что | Замер |
|---|---|
| Всего (RTX A4000) | 16376 MiB |
| Embedding-worker + Rerank-worker (загружены, по ~1.4 GB с CUDA-контекстом) | 2785 MiB |
| + VAD-worker (после первого запроса) | ~3038 MiB |
| Silero TTS | `device=cuda:0` (лог загрузки; co-located в воркер-процессах) |
| GigaAM-v3 | ~1192 MiB на `cuda:0` (после фикса — см. § «Инцидент») |
| **Свободно** | **~12 GB** |

Вывод по бюджету: VRAM **не ограничение**. Qwen3-TTS-1.7B (~3.9 GB) влезает рядом со всеми текущими моделями с большим запасом — CPU-offload embedding/rerank не нужен. Вариант 0.6B остаётся актуальным только как более лёгкий по латентности/стоимости, не по необходимости.

> **Инцидент (найден и закрыт 2026-11-11):** `gigaam-v3-rnnt-ru` в проде не стартовал — при первом запросе `POST /v1/audio/transcriptions` падал `hydra InstantiationException → RuntimeError: Tensor on device cpu is not on the expected device meta!` (цепочка `modeling_gigaam.GigaAMASR → FeatureExtractor`). Корень: transformers 5.x безусловно конструирует модели на meta-device (`low_cpu_mem_usage` мёртв), а remote-код `modeling_gigaam` собирает FeatureExtractor через hydra, где torchaudio `melscale_fbanks` смешивает cpu- и meta-тензоры. **Фикс** (`apps/provider_litserve/stt/engines.py`, коммиты `4a799fee1` + `01e445a3b`): `modeling_gigaam.GigaAMModel` резолвится напрямую через `get_class_from_dynamic_module`, конструируется на CPU, `pytorch_model.bin` заливается `load_state_dict` (0 missing / 0 unexpected), затем `.to("cuda:0")`. Проверено на проде: транскрибация TTS→STT вернула дословный RU-текст, модель на `cuda:0` (~1.2 GiB), health-check кластера зелёный. На проде временно образ `ghcr.io/zamb124/agent-lab-gpu:stt-meta-fix` (дельта поверх `d7e0f46` с тем же кодом) — заменится штатным CI-образом при следующем деплое.

---

## 3. ASR — детально

### 3.1 Self-hosted кандидаты (RU)

| Модель | Параметры | Лицензия | Ключевые RU-метрики | Стриминг | Примечания |
|---|---|---|---|---|---|
| **GigaAM-v3 e2e_rnnt** (текущая) | ~243M | MIT | Офиц. Sber-eval: e2e WER 14.2 / CER 8.8 с нормализацией; F1(,) 84.5, F1(.) 86.7 | Нет (окна 24 с) | Пунктуация+ITN из коробки — оптимально для LLM-потребителя |
| **GigaAM-v3 rnnt / ctc** | ~243M | MIT | Sber-eval avg: RNNT **8.3** / CTC 9.1 (10 RU-доменов); независимый SKILLUM: micro-WER **7.46%** — #1 из 11 конфигов | Нет | Ниже WER, но голый lowercase без пунктуации — хуже как вход LLM |
| **GigaAM-Multilingual large_ctc** (июнь 2026) | 600M | MIT | RU: CV **5.1**, FLEURS **3.0**, in-the-wild **6.0** (vs Whisper large-v3: 9.1/3.1/10.1) | Нет | 70+ языков; CTC → без пунктуации; тот же `AutoModel`+`trust_remote_code` контракт — совместим с нашим `gigaam`-бэкендом |
| **T-One** (`t-tech/T-one`, T-Bank) | 71.7M | Apache-2.0 | Телефония: call-center **8.63**, named-entities **5.83** (лучше GigaAM-v2!); общая речь: CV 5.32 vs GigaAM ~2.7 | **Да** — 300 мс чанки, свой phrase-splitter | Алфавит = 33 кирил. буквы + пробел: нет цифр/латиницы/пунктуации («12 500» → словами). sherpa-onnx build (8 kHz); RTF ~0.2–0.3 на 1 CPU-потоке |
| Whisper large-v3 / turbo | 1.55B / 809M | MIT | RU avg ~21 (Sber-eval); FLEURS-RU 3.5/3.8 (TypeWhisper) | Нет | Бэкенд `whisper` уже есть — baseline, не апгрейд |
| Nemotron 3.5 Transcribe 30B-A4B | 30B MoE (~4.3B act) | открытые веса | FLEURS-RU 2.8 (TypeWhisper) — сильная | Нет | 30B весов не влезает в 16GB → отсева по железу |
| Voxtral Small/Mini (Mistral) | ~24B | Apache-2.0 | RU заявлен, метрик мало | Нет | ~24B не влезает в 16GB → отсева |
| wav2vec2-ru и прочие CTC | — | MIT | Устарели (GigaAM доминирует все RU-домены) | Нет | `huggingface_ctc` бэкенд остаётся как fallback-путь |

**Независимые бенчи RU (сверка):**
- SKILLUM eval (491 запись спонтанной речи, 2026): 1) GigaAM v3 7.46% micro-WER; 2) OpenAI gpt-realtime-whisper 8.52%; 3) faster-whisper large-v3 9.78%; дальше Deepgram nova-3, Sber, Yandex.
- TypeWhisper FLEURS-RU (clean): gpt-4o-transcribe 1.9%, Soniox v6 2.5%, Nemotron 3.5T 2.8%, **GigaAM v3 RNNT 3.5%**, whisper-large-v3 3.5%, turbo 3.8%.
- vladmesh/ru-it-stt-eval (RU IT-подкасты, авг 2026): Scribe v2 — лидер fair head-to-head; далее gpt-transcribe, MAI-Transcribe 1.5.

### 3.2 Вердикт ASR

`e2e_rnnt` — правильный выбор для нашего пайплайна: транскрипт идёт в LLM-агента и в ленту сообщений, пунктуация/ITN обязательны; в таблице «сырого WER» e2e выглядит хуже только из-за протокола оценки (её постобработку вычитают из метрики). Замены «на что-то лучшее» для self-hosted RU на ноябрь 2026 **нет** — GigaAM остаётся open SOTA.

Что дало бы реальный прирост:
1. **Partial-стриминг**: сейчас сессия буферизует и бьёт по VAD — промежуточных гипотез нет. T-One (Apache-2.0, CPU-friendly, телефония-домен) или sherpa-onnx-сборка GigaAM — кандидаты на слой partials; GigaAM остаётся финальным распознавателем.
2. **GigaAM-Multilingual-600M** как вторая запись каталога: на всякий многоязычный кейс (en/kk/ky/uz) и как независимая проверка на «диких» данных (officially лучший open по RU на их internal-сете: 6.0).
3. **Word-level timestamps** — фича апрельского 2026-обновления GigaAM: полезна для UX (подсветка слов, точное выравнивание субтитров в sync) — уточнить поддержку в нашем адаптере.
4. Смежно: `GigaAM-Emo` (та же линейка, MIT) — определение эмоций в голосе; потенциальный апсейл-фич для voice-агентов.

### 3.3 Cloud ASR — эталон и fallback

| Провайдер | RU-качество | Стриминг | Комментарий |
|---|---|---|---|
| ElevenLabs Scribe v2 / v2 Realtime / Scribe v3 Live | Лидер ru-it-stt-eval; verli RU ~6.5; AA-WER #1 (июль 2026) | Realtime ~150 мс, partial+committed, keyterms | Лучший облачный эталон; новый провайдер в resolver — работа L |
| OpenAI gpt-4o-transcribe / gpt-realtime-whisper | FLEURS-RU 1.9%; #2 SKILLUM (realtime) | Realtime API есть | Доступен ли через наш cloud.ru-контур — вопрос; напрямую — новый клиент |
| Soniox v6 | FLEURS-RU 2.5% | Да | Сильный, низкая цена; новый клиент |
| Sber SaluteSpeech | STREAMING лучший из РФ-облака в SKILLUM (10.86) | Да (в т.ч. 2-канал) | 0.6 ₽/мин (~36 ₽/ч); клиент у нас stub → доработка |
| Yandex SpeechKit v3 | 11.8–13.0 в SKILLUM | Да | ~39 ₽/ч стриминг; клиент stub → доработка |
| cloud.ru whisper-large-v3 (текущий) | ~21 avg RU — заметно хуже GigaAM | Нет | 0.0061 ₽/с (~22 ₽/ч); держать как fallback, не как дефолт качества |

---

## 4. TTS — детально (главный разрыв)

### 4.1 Лицензионный блок — P0

Первоисточник (`snakers4/silero-models`, раздел Licence): *«All of the models are published under the main repo license (i.e. CC-NC-BY) except for the base cis-tts models, which are under MIT»*.

- `v5_ru`…`v5_6_ru` (наш дефолт `v5_5_ru`) — **CC BY-NC 4.0**: коммерческое использование запрещено без Enterprise-лицензии Silero (CE/EE-тиers есть в их wiki).
- MIT только у `v5_cis_base` / `v5_cis_base_nostress` — те же голоса с префиксом `ru_`, но **без авто-ударений и разрешения омографов** (ручная разметка `к+ошка`).
- Если EE-лицензия Silero уже куплена — лицензионный пункт снимается, остаётся только качественное отставание.

### 4.2 Self-hosted кандидаты (коммерчески чистые)

| Модель | Размер | Лицензия | RU-метрики | Стриминг | VRAM-оценка | Примечания |
|---|---|---|---|---|---|---|
| **Qwen3-TTS-12Hz-0.6B** (CustomVoice/Base) | 0.6B (~1.8 GB веса) | Apache-2.0 | RU WER 4.458 (Base) / SIM 0.781 — офиц. карточка; на ZTTS1-Eval RU 1.7B-версия 3.88 | ~97–101 мс first-packet | ~1.8–2.5 GB | 10 языков вкл. RU; 9 пресетов без нативно-русского голоса → RU через Base-клонирование по референсу или VoiceDesign |
| **Qwen3-TTS-12Hz-1.7B** (CustomVoice/VoiceDesign/Base) | 1.7B (~3.9 GB измерено) | Apache-2.0 | **RU WER 3.212 — лучший open по русскому** (ElevenLabs 3.878, MiniMax 4.281); SIM 0.792 | ~101 мс | ~3.9 GB — **влезает** (свободно ~13 GB по замеру прод 2026-11-11) | **Топ-1 рекомендация по качеству**; vLLM-Omni поддерживает (offline пока) |
| **Fun-CosyVoice3-0.5B(-2512)** (+RL) | 0.5B | Apache-2.0 | RU заявлен (9 языков); независимых RU-метрик мало; CV3-Eval: en WER 1.68–2.24, SIM 71.8–77.4 — сильнее CosyVoice2 | Bi-stream ~150 мс | ~1.5–2 GB | По офиц. таблице — одна из лучших open per-size; Balalaika-Longform (arxiv 2610): лучший длинный RU-синтез после long-target FT |
| **ESpeech-TTS-1_RL-V2** | ~0.35B (F5 DiT) | Apache-2.0 (карточка) | RU-нативная; авто-ударения через RUAccent (MIT); Habr-обзор raft: естественность 4.5/5, быстрая | Нет | ~1–1.5 GB | Русскоязычная команда; клонирование по референсу ≤12 с; single-maintainer — зрелость ниже; проверить: карточка Apache-2.0 vs происхождение от F5 (CC-BY-NC базы) |
| **Chatterbox Multilingual v3** | 0.5B | MIT | RU в списке 23 языков; качество RU не бенчено независимо | Нет | ~1.5–2 GB | Проект **retired** (Resemble ушёл из TTS, авг 2026, без обновлений); PerTh-watermark на каждый выход — коммерчески легально, но аудио помечается |
| **Silero v5_cis_base_nostress** (ru_* голоса) | ~150 Mi | MIT | Качество как у v5, но **без авто-ударений/омографов** → много фонетических ошибок на живом тексте | Нет | ~0.15 GB | Легальный Silero-фолбэк; требует внешнего акцентуатора (ruaccent MIT — см. ниже) |
| **Silero v5_6_ru** | ~150 Mi | **CC BY-NC** | Как v5_5_ru + Emphasis/Exclamations | Нет | ~0.15 GB | Только если решён вопрос EE-лицензии; `silero` pip уже умеет (models.yml с master) — правка allowlist `SILERO_TTS_RU_V5_BUNDLES` |

**Отсеянные по лицензии**: Fish S2-Pro/Drama3 (Research-лицензия, коммерция за отдельную лицензию), F5-TTS_RUSSIAN от Misha24-10 (CC-BY-NC базы), OmniVoice (веса CC-BY-NC), XTTS-v2 (Coqui CPML — некоммерческая + устарел), VoxCPM2 (проверить; на ZTTS1-Eval RU 5.37 — слабее лидеров), Kokoro (RU слабый).

**Русская специфика — критично**: авто-ударения и омографы. Silero решает это rule-based внутри модели. У LM-based TTS (Qwen3/CosyVoice3/ESpeech) — через текстовое понимание; независимых RU-тестов омографов у них почти нет. Исторический Habr-тест (2024, устарел, но индикативен): Silero-v4 — 16/30 ошибок на омографах, Sber 5, Yandex 4. Рекомендованный путь для open-модели — внешний акцентуатор **ruaccent** (MIT по репозиторию; на PyPI висит оговорка «по вопросам коммерческого использования пишите в telegram» — **требует юридической сверки**) или `+ударения`-маркеры через наш `tts_input_steps` (реестр уже есть).

### 4.3 Cloud TTS — эталон и fallback

| Провайдер | RU-качество | Стриминг/латентность | Цена (нояб 2026) | Комментарий |
|---|---|---|---|---|
| Yandex SpeechKit | Топ для RU; новые **LiveTTS**-голоса (с 24.09.2026, Realtime API) | Realtime API 0.25 ₽/блок 250 симв | API v3 general 0.1626 ₽/блок, LiveTTS 0.25 ₽/блок (~650–1000 ₽/1М симв) | 152-ФЗ; амплуа; Brand Voice Lite 9150 ₽ + 101.7к ₽/мес; клиент stub → доработать |
| Sber SaluteSpeech | Сопоставимо с Yandex (9/10) | Да | 0.000186 ₽/симв (~186 ₽/1М) — дешевле всех облаков; мин. 15к ₽/мес | YourVoice для брендового голоса; новые клиенты — только корп.-пакеты с 15.07.2026; клиент stub |
| ElevenLabs v3/v4 | RU хорошая, не топ (ZTTS1-Eval RU 4.28) | ~100–165 мс server | $/кредиты | Эталон качества «на запад»; data-residency вопрос |
| Cartesia Sonic 3.5 | **ZTTS1-Eval RU WER 3.75 — лидер** | Стриминг | $ | Дорого, non-RU резидентство |
| Gemini 3.1 Flash TTS | ZTTS1-Eval RU 3.77 | — | $ | Через Vertex/Google |
| cloud.ru tts-1(-hd) (текущий) | OpenAI-совместимая, RU средняя | — | ~ | Оставить fallback |

---

## 5. VAD и turn-detection

| Модель | Лицензия | Статус | Вердикт |
|---|---|---|---|
| **silero-vad 6.2.3** (текущая) | MIT | Последняя версия (Sep 2026); v6 (авг 2025): −16% ошибок на шумных данных, −11% multi-domain; 8/16 kHz; ~2 МБ | ✅ Держать. Лучшая open VAD и единственная с 8 kHz для телефонии |
| TEN-VAD | Apache-2.0 + условия Agora | Лучшая скорость детекции конца речи, но лицензия запрещает деплой, конкурирующий с Agora | ❌ Отсева по лицензии |
| FireRedVAD | Apache-2.0 | 16 kHz only, ~0.6M параметров | Резерв, преимуществ над Silero v6 не доказано |
| NVIDIA MarbleNet / pyannote-3.0 / FunASR fsmn-vad | разные | Ниши: офлайн-диаризация и пр. | Не для realtime-сессии |

**Смежный апгрейд — semantic end-of-turn** (не замена VAD, а слой поверх для endpointing/barge-in):
- `pipecat-ai/smart-turn-v3`: BSD-2-Clause, Whisper-Tiny encoder + линейная голова, 8 МБ ONNX int8, CPU ~12 мс, multilingual (RU-покрытие заявлено тегом — проверить эмпирически на наших данных; есть per-language fine-tunes).
- LiveKit turn-detector `v1-mini`: open-weights, но текстовый (нужен транскрипт) — у нас partial-транскрипта пока нет → зависит от пункта «partial STT».
- Эффект: точное определение конца реплики → меньше ложных перебиваний при паузах «мне надо подумать». Кандидат P3.

---

## 6. Roadmap апгрейда

Приоритеты: P0 — блокеры/риски, P1 — высокая ценность при умеренной цене, P2 — улучшения, P3 — опционально.

### P0 — Лицензия Silero TTS (compliance-риск)

**Проблема**: `silero-tts-v5-5-ru` под CC BY-NC — для коммерческого продукта легально только с EE-лицензией Silero.
**Ветки решения** (выбрать одну — решение бизнеса/юристов):
- **A. Купить EE-лицензию** Silero → тогда бамп на `v5_6_ru` (Emphasis/Exclamations): правка `SILERO_TTS_RU_V5_BUNDLES` + `SILERO_V5_RU_SPEAKERS_BY_BUNDLE` в `core/config/models.py`, новая запись каталога `/litserve`. Трудоёмкость: **S**.
- **B. Мигрировать на permissive-модель** → см. P1.
- **C. Временный легальный фолбэк**: `v5_cis_base_nostress` (MIT) + `tts_input_steps` с ruaccent-маркировкой — если нужно «прямо сейчас». Трудоёмкость: S–M, качество ниже.

### P1 — Новый TTS-бэкенд (основной апгрейд)

**Рекомендация**: **Qwen3-TTS-12Hz-1.7B** как новый default (по замеру 2026-11-11 свободно ~12 GB VRAM — влезает напрямую, без CPU-offload).
- Русский голос: Base с 3-сек референсом RU-голоса (клонирование) — пресеты CustomVoice нативно-русского не имеют.
- Вариант экономии VRAM/латентности: `0.6B-CustomVoice` или `0.6B-Base` (~1.8–2.5 GB, RU WER 4.458) — A/B на текстах платформы против 1.7B.
- Что трогать: `ProviderLitserveTTSModelEntry.backend` (Literal["silero"] → +`"qwen3_tts"`), `apps/provider_litserve/tts/engines.py` (новый адаптер поверх `qwen-tts`/`transformers`), поля записи (voice→speaker/voice_clone_ref, sample_rate→native 24k), warmup, allowlist голосов в `speech_provider_catalog.py`, зависимость в `litserve` extras, seed в `infra.tts_models`. Трудоёмкость: **M–L**.
- Риски: CUDA-only (ок — GPU-под); RU-омографы без rule-стресса (проверить на текстах платформы, при необходимости ruaccent-шаг); vLLM-стриминг ещё развивается — на старте держать батч-режим поверх существующего сегментного пайплайна.
- Альтернатива той же цены: **CosyVoice3-0.5B-2512_RL** (Apache-2.0, ~150 мс, чуть компактнее) — держать запасным кандидатом, A/B на наших текстах.
- Дешёвый RU-нативный вариант: **ESpeech-TTS-1_RL-V2** (Apache-2.0 карточка, авто-ударения) — single-maintainer, зрелость ниже; кандидат «на посмотреть».

### P1 — STT: уточнение и расширение каталога

- Добавить записи каталога: `ai-sage/GigaAM-Multilingual` `large_ctc` (600M, MIT, RU + en/kk/ky/uz) и при желании `v3_rnnt` для сырого-WER кейсов — бэкенд `gigaam` уже совместим; проверить `.transcribe()`-контракт у multilingual. Трудоёмкость: **S**.
- Проверить, что `e2e_rnnt` остаётся дефолтом голосового контура (пунктуация для LLM) — вердикт: оставить.
- Word-level timestamps (апрель 2026): уточнить API (`transcribe` возвращает только str сейчас) — задел для фич субтитров. Трудоёмкость: S–M.

### P1 — Partial-стриминг STT (UX голосовых сессий)

- **T-One** (Apache-2.0): слой partial-транскриптов в `stt_worker` (300 мс чанки, ~0.6–1.0 с до фразы, CPU-only вариант через sherpa-onnx — разгружает GPU). Ограничение: только кириллица+пробел → partials «сырые», финал — через GigaAM e2e. Трудоёмкость: **M** (новый provider/bакенд, новый dep `tone`/`sherpa-onnx`).
- Альтернатива: sherpa-onnx-экспорт GigaAM (online-streaming через buffered окна, ~0.8 с stride) — хуже латентность, но единый стек.

### P2 — Облачные fallback-и

- Доработать stub-клиенты **Yandex SpeechKit** (API v3 + Realtime + LiveTTS-голоса) и **Sber SaluteSpeech** — они в allowlist, но не реализованы; лучшие RU-облака и 152-ФЗ-резидентство. Трудоёмкость: **M каждый**.
- Оценить нового провайдера **ElevenLabs** (Scribe v2 Realtime ~150 мс + TTS v3/v4): лучший облачный эталон; резидентность/152-ФЗ — на юристов. Трудоёмкость: **L** (новый клиент + resolver + billing-ставки).
- `cloud.ru` оставить как есть (whisper-large-v3 STT ~22 ₽/ч, tts-1(-hd)) — доступных новых аудио-моделей у них в каталоге не видно (Oct 2026).

### P3 — Turn-detection и смежное

- `smart-turn-v3` (BSD-2, 8 МБ ONNX, CPU) как слой endpointing в `BargeInController` — снизить ложные перебивания. Трудоёмкость: **M**; зависит от эмпирической проверки RU.
- `GigaAM-Emo` (MIT) — эмоции в голосе как фича (аналитика звонков). Трудоёмкость: S–M.
- Собственные бенчи: собрать 50–100 записей реального трафика (voice-сессии + sync-голосовые) → прогон `e2e_rnnt` vs `v3_rnnt` vs Multilingual-600M vs облачного эталона; для TTS — слушательский тест 5–7 моделей на текстах платформы (омографы, числа, имена). Трудоёмкость: M. **Это обязательный шаг перед финальной миграцией TTS** — литературные метрики RU-TTS разбросаны.

---

## 7. Таблица «устарело / актуально» — финальная сводка

| Модель | Возраст/версия | Состояние на 11.2026 | Действие |
|---|---|---|---|
| GigaAM-v3 `e2e_rnnt` | Nov 2025 | Open SOTA RU ASR; Multilingual-600M — сосед-апгрейд на будущее | Keep + опционально каталог-записи |
| Silero TTS `v5_5_ru` | ~2025 | CC BY-NC; качество ниже Qwen3-TTS | **ЗАМЕНЁН на Qwen3-TTS 1.7B CustomVoice (прод, 2026-11-11)** |
| silero-vad 6.2.3 | Sep 2026 | Последняя версия, MIT | Keep |
| (отсутствует) partial-STT | — | Пробел в UX голосовых сессий | P1 T-One / sherpa |
| Yandex/Sber клиенты | stub | Лучшие RU-облака не подключены | P2 доработка |
| cloud.ru whisper/tts-1 | текущий | Легитимный fallback, не лидер | Keep |

---

## 8. Источники (дата обращения — 2026-11-11)

**Первоисточники:**
- `github.com/salute-developers/GigaAM` — evaluation.md (v3 WER-таблица, Multilingual eval, e2e F1/WER, Emo), HF `ai-sage/GigaAM-v3`, `ai-sage/GigaAM-Multilingual` (MIT; релиз Multilingual — июнь 2026).
- `github.com/snakers4/silero-models` — README (таблица v5-бандлов: `v5_6_ru` = Emphasis/Exclamations; Licence: CC-NC-BY кроме `v5_cis_base*` MIT), PyPI `silero-vad` 6.2.3 (Sep 2026), GitHub releases v6.0 (Aug 2025).
- `huggingface.co/Qwen/Qwen3-TTS-12Hz-*` (Apache-2.0; RU WER 3.212/4.458, SIM 0.792; streaming 97–101 мс; список 9 пресетов; vLLM-Omni support), tech report arXiv 2601.15621.
- `huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512` (Apache-2.0; 9 языков вкл. RU; bi-stream ~150 мс; CV3-Eval таблица).
- `huggingface.co/t-tech/T-one` + `github.com/voicekit-team/T-one` (Apache-2.0; телефония-бенчи; 300 мс чанки).
- `huggingface.co/ESpeech/ESpeech-TTS-1_RL-V2` (Apache-2.0; F5 DiT + RUAccent), `github.com/Den4ikAI/ruaccent` (MIT).
- `huggingface.co/pipecat-ai/smart-turn-v3` + `github.com/pipecat-ai/smart-turn` (BSD-2-Clause, multilingual, 8 МБ ONNX).
- `github.com/resemble-ai/chatterbox` (MIT; Multilingual v3 июнь 2026; retired авг 2026 + PerTh watermark).
- Документация провайдеров: `developers.sber.ru` SaluteSpeech (голоса Nec/Bys/May/Tur/Ost/Pon/Kin; 0.000186 ₽/симв, 0.6 ₽/мин; ограничения новых клиентов с 15.07.2026), `yandex.cloud` SpeechKit (LiveTTS с 24.09.2026; API v3 тарифы), `elevenlabs.io` (Scribe v2 Realtime ~150 мс, v3 Live; latency methodology Oct 2026), `cloud.ru` Foundation Models (whisper-large-v3, 0.0061 ₽/с).

**Независимые бенчи:** SKILLUM ASR eval (491 запись), TypeWhisper STT benchmark (FLEURS-RU), vladmesh/ru-it-stt-eval (авг 2026), SOTA2 ZTTS1-Eval in-the-wild RU (июнь 2026), dev.to CPU-бенч T-one/GigaAM-v3 (сен 2026), Balalaika-Longform (arXiv 2610), raft Habr-обзор open TTS, dograh VAD-сравнение 2026, Cekura Silero-vs-TEN.

**Помечено как unverified:** реальные ready-записи `provider_litserve_models` в проде (известны только seed-дефолты + подтверждённый ответ `/v1/models`: embedding, reranker, `gigaam-v3-rnnt-ru` видны в каталоге); RU-покрытие smart-turn-v3 на наших данных; легальность статуса ruaccent (MIT в репо vs оговорка о коммерческом использовании на PyPI); Apache-2.0 карточка ESpeech vs наследование от CC-BY-NC баз F5; наличие EE-лицензии Silero у компании.

**Замерено на проде 2026-11-11:** GPU RTX A4000 16GB; embedder+reranker 2785 MiB, +VAD ~3038 MiB, +GigaAM ~4230 MiB, TTS на `cuda:0`, свободно ~12 GB; `gigaam-v3-rnnt-ru` падал при загрузке (meta-device ошибка transformers 5.x → STT 500) — **исправлено** (§ «Инцидент», коммиты `4a799fee1` + `01e445a3b`, прод верифицирован); устаревший комментарий «RTX A2000 6GB» в `values.yaml` исправлен.


---

## 9. Миграция TTS: Silero → Qwen3-TTS — выполнено и верифицировано на проде (2026-11-11)

**Статус:** DEPLOYED + VERIFIED. Локальный TTS теперь `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`
(Apache-2.0) — P0-лицензионный риск Silero CC BY-NC закрыт.

**Верификация на проде** (`provider-litserve-7f9974cd9f-qj7q6`, образ `ghcr.io/zamb124/agent-lab-gpu:qwen3-tts`):

| Проверка | Результат |
|---|---|
| Загрузка модели | `load_seconds=14.3` (HF-кэш на PVC), READY |
| GPU | воркер 4338 MiB на `cuda:0` (nvidia-smi); всего ~7.4/16 GiB |
| Синтез RU | `POST /v1/audio/speech` → WAV 24 kHz mono, 2.56 с (122 924 B) |
| Цепочка TTS→STT | GigaAM транскрибация Qwen-речи → дословный текст (7.6 с) |
| Смена спикера | `voice=vivian` → WAV 61 КБ; дефолт `serena` |
| Невалидный голос | `voice=xenia` → ошибка (не молчаливый фолбек) |
| Старая модель | `model=silero-tts-v5-5-ru` → ошибка unknown model |
| Каталог | `/v1/models`: единственный TTS — `qwen3-tts-1.7b-customvoice-ru` |
| Удаление Silero | строка `deleting` → `deleted` ops-циклом (веса вычищены) |

**Найденный и закрытый прод-баг:** transformers 5.x сделал `MimiModel.upsample`/`decoder_transformer`
read-only @property → вендорный `Qwen3TTSTokenizerV2Encoder` падал на `self.upsample = None`.
Фикс `_apply_qwen_tts_encoder_compat` в `tts/engines.py` (коммит `7de249333`).

**Известная неидеальность:** при загрузке весов токенизера transformers логирует
`MISSING encoder_seanet.layers.*.conv.bias` — инициализация дефолтом; эмпирически
не влияет (дословная TTS→STT-цепочка подтверждена), стоит отслеживать апстрим issue.

**Дрейф прода:** под на образе `qwen3-tts` (дельта поверх `stt-meta-fix`, собран на ноде),
деплой через `kubectl set image`. Канонический образ появится при следующем CI-деплое
после пуша коммитов (`240551cd6`, `7de249333`). Helm rev 143 завис в `pending-upgrade`
(сессия умерла на `Preparing upgrade`) — следующий `make k8s-deploy` снимет.
