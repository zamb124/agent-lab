---
name: backend-engineer
description: "Backend-разработка Платформы: новая фича или багфикс в Python (core/**, apps/**, tests/**) — модели Oxyde, сервисы, op_* и REST-зеркало, Service Kit DI, TaskIQ, события, миграции, тесты. Использовать при любой правке backend-кода; выравнивание существующего кода под канон — скил refactor-engineer."
---

# Backend Engineer

Процедура backend-изменения. Нормы — в `.cursor/rules/`; скил их не пересказывает.

## Перед правкой

1. `main.mdc` и `architecture.mdc` (всегда в контексте) и правило домена `.cursor/rules/<домен>.mdc` целиком. По задаче: таблицы — `database.mdc`; права — `authorization.mdc`; фоновые задачи — `taskiq.mdc`; события — `events.mdc`; деньги — `billing.mdc`; модели ИИ — `ai_models.mdc`; тесты — `testing.mdc`.
2. Поиск аналога: `core/` → сервис-владелец (`main.mdc` § Владельцы сущностей) → граф и `rg` (`AGENTS.md`). Совпал смысл — расширяется существующее.
3. Место кода — тест `main.mdc` § Куда писать код: модель → сервис → операция.

## Порядок реализации

1. **Модель.** `apps/<svc>/models/<entity>.py`, `@classmethod` на `cls.objects`, имя по `database.mdc` § Имена методов. Новая таблица или колонка — следующий файл `migrations/<db>/NNNN_<name>.py` через `makemigrations`.
2. **Сервис.** Метод с именем логики: Check, инварианты, `publish_event_*`, `enqueue`. Зависимости — параметры конструктора; Kit соберёт их по типам.
3. **DI.** Поле `apps/<process>/di.py` — только если его читает boundary; конфиг → примитивы или ресурс с teardown — `@recipe` (`architecture.mdc` § Service Kit DI).
4. **Команда.** Payload и результат → `op_<entity>_<verb>` → `<SVC>_OPERATIONS` → REST-зеркало → UI-фабрика (`architecture.mdc` § Новая команда).
5. **Тесты.** Инвариант поведения на реальной инфраструктуре (`testing.mdc`); команда — тождество WS ≡ REST в `tests/realtime/test_<svc>_commands.py`.
6. **Правило-владелец.** Новая сущность, поле, паттерн или гейт записываются в правило домена в том же изменении (`rules.mdc`).

## Проверка

- Во время работы — `make lint <path>`; перед завершением — `make lint`. Полный список падений без остановки — `uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py`.
- `make test-up` один раз, затем `uv run pytest tests/<домен>/ -q`; после изменения DI, транспорта или контрактов — архитектурные тесты из `references/testing.md`.
- Права и dual-write: `uv run python scripts/check_authz_canon.py`, `uv run python scripts/check_authz_dual_write.py`.
- Задача завершена, когда lint зелёный (падения до изменения доказаны baseline) и тесты домена проходят.

## References

- `.cursor/skills/backend-engineer/references/testing.md` — тестовый стек, профили, триаж, команды слоёв тестов.
