# Гейты

Норма → гейт закреплены в разделе «Гейты» правила-владельца. Исполняемый список — `scripts/gates/registry.py`. Здесь — как гейты запускать и читать.

## Состав `make lint`

- `make lint` = `_lint-py` + `lint-ts` (`mk/lint.mk`). `make lint <path>` — ruff + basedpyright на файл (`.py`) или `lint-ts` (`.js`, `.ts`).
- `_lint-py` = `ruff check apps core` + `python -m scripts.gates --suite lint` + basedpyright + `analyze_imports.py`.
- `lint-ts` = `tsc -p tsconfig.json` + `python -m scripts.gates --suite lint_ts`.
- Сьют `lint_ts` включает бывший `check-events-canon`, кроме гейтов, которые уже в `lint` (файлы, MCP branding), плюс UI Kit, field canon и logging.
- `make test-static` = `_lint-py` + `python -m scripts.gates --suite static` + `tests/core/ai/test_platform_model_scoring_fixtures.py`. Сьют `static` — `scripts/generate/a2a_fixtures.py --check`.
- Сьют `network` — `scripts/gates/repo/ft_wheels.sh` и `scripts/generate/a2a_fixtures.py --check-remote`. Цель `make check-gpu-dockerfile-llm-model` — `scripts/gates/repo/gpu_dockerfile_llm_model.sh`. Документация — `scripts/gates/repo/docs_locale_parity.py`, `scripts/gates/repo/scenario_docs_quality.py`.
- Отчёты без fail: `scripts/tools/report_ui_i18n_gaps.py`, `scripts/tools/report_ui_kostyli.py`.

Прогон одного гейта: `uv run python -m scripts.gates --gate <name>` или `uv run python -m scripts.gates.<область>.<модуль>`. Имена — `python -m scripts.gates --list`.

## Пакеты `scripts/gates`

| Пакет | Что держит |
|---|---|
| `backend/` | импорты, команды и REST, DI, запрещённые пути, ratchet, один `PlatformModel` на файл, миграции, Redis, TaskIQ, billing, ошибки, события, realtime, logging, Granian |
| `authz/` | OpenFGA: канон, dual-write, backfill, модель |
| `files/` | Files API, object store, `FileReader`, `file_id`, корпус, UI upload |
| `voice/` | `voice_resolver`, speakable, один apply TTS-пайплайна |
| `ai/` | модели только через `core.ai`, один реранк |
| `flows/` | tags и контракты tools, MCP branding, Flow UI hard cut |
| `sync/` | `op_adapters.py` — `op_*` зовут сервис |
| `frontend/` | UI canon, field canon, фабрики, UI Kit, core frontend, embed ESM, i18n |
| `repo/` | гигиена корня, `conf.json`, бренд, переменные, колёса, layout скриптов, документация |

Смежные пакеты не гейты: `dev/` — `run.py` и bootstrap; `db/` — миграции; `testing/` — стек pytest; `build/` — UI и i18n; `docs/` — Zensical; `generate/` — фикстуры и ассеты; `tools/` — диагностика и отчёты.

## Чтение вывода

- Гейт собирает нарушения и выходит с 1. `python -m scripts.gates --suite` не останавливается на первом гейте: в конце строка `gates: N ran, M failed`.
- `make lint` останавливается, если упал ruff, сьют или basedpyright. Полный отчёт по шагам — `gates_report.py`: он читает `--list`, а не рецепт Makefile.
- Мягкие режимы: `scripts/gates/frontend/i18n_keys.py` без `--strict`, `scripts/gates/backend/command_rest_mirror.py` и `scripts/gates/frontend/ui_factories.py` без `--strict` печатают предупреждения без fail. В сьют `lint_ts` ключи i18n входят с `--mode missing --strict`.
- Ratchet: рост — FAIL; снижение — OK и подсказка `--update`. Файлы по метрике — `.cursor/skills/refactor-engineer/scripts/ratchet_list.py <metric>`. Текущее число ниже baseline — `uv run python -m scripts.gates.backend.ratchet_counts --update`.
- `analyze_imports.py`: читать `Total local imports`, а не код выхода.

## Allowlist: принцип или долг

- Принцип (не сокращается срезом): `PROTOCOL_HANDLERS`, `COMMAND_WS_HTTP_ALLOWLIST`, инфраструктурные точки Redis/TaskIQ, billing entrypoints, allowlist корня репозитория, `FGA_ONLY_*`. Каждый пункт — `Исключение:` в правиле-владельце.
- Долг (сокращается срезами до 0): ratchet-baseline, `scripts/gates/backend/backend_error_i18n_baseline.json`, пути в `ALLOWLIST_PATHS`, не оформленные `Исключение:` в правиле.
- Новый пункт allowlist ради зелёного прогона запрещён; принципиальный — только вместе с `Исключение:` в правиле-владельце.
