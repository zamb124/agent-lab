#!/usr/bin/env bash
# Проверка единого канона логирования платформы.
#
# Гарантирует, что прикладной код использует только core.logging.get_logger,
# не пишет файлы из контейнеров, не оставляет print() и эмодзи в строках,
# и инициализирует TaskIQ воркеры через core.tasks.broker.register_worker_events.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
    echo "check_logging_canon: нужен ripgrep (rg)" >&2
    exit 1
fi

ERR=0
fail() { echo "check_logging_canon: $1" >&2; ERR=1; }

PY_GLOBS=(
    apps core
    --type py
    --glob '!**/migrations/versions/**'
    --glob '!**/__pycache__/**'
    --glob '!core/docs/data/python/**'
    --glob '!apps/agent/desktop/vendor/**'
)

# 1. Запрет logging.getLogger(...) в прикладном коде.
#    Допустимо только в core/logging/setup.py (root logger / fan-out),
#    в core/tracing/tracer.py (silencing OTEL внутренних логгеров),
#    в core/logging/processors.py (аварийная запись при DropEvent — минуя pipeline),
#    и в core/logging/__init__.py (комментарий-описание самого канона).
LOGGER_GETLOGGER_GLOBS=(
    "${PY_GLOBS[@]}"
    --glob '!core/logging/setup.py'
    --glob '!core/logging/__init__.py'
    --glob '!core/logging/processors.py'
    --glob '!core/tracing/tracer.py'
)
if rg -nq 'logging\.getLogger\s*\(' "${LOGGER_GETLOGGER_GLOBS[@]}"; then
    fail "logging.getLogger(...) запрещён вне core/logging/setup.py — используйте core.logging.get_logger(__name__)"
    rg -n 'logging\.getLogger\s*\(' "${LOGGER_GETLOGGER_GLOBS[@]}" >&2 || true
fi

# 2. Запрет ручного создания get_logger через старый импорт-паттерн.
if rg -nq 'from\s+core\.logging\.logger\s+import' "${PY_GLOBS[@]}"; then
    fail "core.logging.logger удалён — используйте 'from core.logging import get_logger'"
    rg -n 'from\s+core\.logging\.logger\s+import' "${PY_GLOBS[@]}" >&2 || true
fi

# 3. Запрет файловых хендлеров в прикладном коде.
FILE_HANDLER_GLOBS=(
    "${PY_GLOBS[@]}"
    --glob '!core/logging/**'
    --glob '!scripts/**'
)
if rg -nq '\b(RotatingFileHandler|TimedRotatingFileHandler|FileHandler)\b' "${FILE_HANDLER_GLOBS[@]}"; then
    fail "файловые хендлеры запрещены — все логи только в stdout"
    rg -n '\b(RotatingFileHandler|TimedRotatingFileHandler|FileHandler)\b' "${FILE_HANDLER_GLOBS[@]}" >&2 || true
fi

# 4. Запрет print(...) в apps/** и core/** (кроме sandbox-runner'ов и
#    doctest-блоков в docstring'ах — определяется AST-обходом).
PRINT_OUT=$(uv run --no-project python scripts/_check_print_calls.py apps core 2>/dev/null || true)
if [ -n "$PRINT_OUT" ]; then
    fail "print(...) запрещён в прикладном коде — используйте core.logging.get_logger(__name__)"
    echo "$PRINT_OUT" >&2
fi

# 5. Запрет эмодзи в любом logger.* вызове (в т.ч. многострочном).
#    Эмодзи в логах ломают grep/Loki-фильтры и нарушают контракт записи.
if rg -nUP --multiline 'logger\.[a-z_]+\([^)]{0,800}[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{1F000}-\x{1F2FF}\x{1F600}-\x{1F64F}\x{1F680}-\x{1F6FF}\x{2300}-\x{23FF}]' "${PY_GLOBS[@]}" >/dev/null 2>&1; then
    fail "эмодзи в logger.* запрещены — message должен быть машинно-читаемым event-ID"
    rg -nUP --multiline 'logger\.[a-z_]+\([^)]{0,800}[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{1F000}-\x{1F2FF}\x{1F600}-\x{1F64F}\x{1F680}-\x{1F6FF}\x{2300}-\x{23FF}]' "${PY_GLOBS[@]}" >&2 || true
fi

# 6. Запрет setup_logging внутри сервисных broker.py — только через
#    core.tasks.broker.register_worker_events / create_service_app.
WORKER_BROKER_FILES=$(find apps -path 'apps/*_worker/broker.py' -o -path 'apps/sync/realtime/broker.py' 2>/dev/null || true)
if [ -n "$WORKER_BROKER_FILES" ]; then
    for f in $WORKER_BROKER_FILES; do
        if rg -nq 'setup_logging\s*\(' "$f"; then
            fail "$f: прямой setup_logging запрещён — используйте register_worker_events(...) из core.tasks.broker"
            rg -n 'setup_logging\s*\(' "$f" >&2 || true
        fi
    done
fi

# 7. Контроль asyncio.create_task: должен идти через
#    core.utils.background.run_with_log_context(coro, name=...). Известная
#    инфраструктура (WS proxy, Redis loops, LitServe internals, A2A collector,
#    polling triggers) пока вынесена из этого правила, чтобы миграция была
#    инкрементальной — но новые случаи в продуктовом коде уже под запретом.
CREATE_TASK_GLOBS=(
    "${PY_GLOBS[@]}"
    --glob '!core/utils/background.py'
    --glob '!core/tasks/**'
    --glob '!core/scheduler/**'
    --glob '!core/websocket/manager.py'
    --glob '!core/middleware/dev_inter_service_proxy.py'
    --glob '!apps/provider_litserve/**'
    --glob '!apps/flows/src/channels/a2a.py'
    --glob '!apps/flows/src/triggers/dev_polling.py'
    --glob '!apps/sync/realtime/speech_to_chat_workflow.py'
)
if rg -nq 'asyncio\.create_task\s*\(' "${CREATE_TASK_GLOBS[@]}"; then
    fail "asyncio.create_task(...) запрещён — используйте core.utils.background.run_with_log_context(coro, name=...)"
    rg -n 'asyncio\.create_task\s*\(' "${CREATE_TASK_GLOBS[@]}" >&2 || true
fi

# 8. Контроль logger.* с f-строкой как первым аргументом: миграция на kwargs
#    идёт инкрементально, поэтому фиксируем верхнюю границу — новые случаи не
#    добавляются. Снижайте F_LIMIT по мере вычистки кодовой базы.
if rg -nq "logger\.[a-z_]+\(\s*f['\"]" "${PY_GLOBS[@]}"; then
    F_COUNT=$(rg -c "logger\.[a-z_]+\(\s*f['\"]" "${PY_GLOBS[@]}" 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
    F_LIMIT=650
    if [ "$F_COUNT" -gt "$F_LIMIT" ]; then
        fail "logger.* с f-строкой превышает лимит ($F_COUNT > $F_LIMIT) — переводите на kwargs: logger.info('event.id', key=value, ...)"
    else
        echo "check_logging_canon: warn — logger.* с f-строкой: $F_COUNT (лимит $F_LIMIT)" >&2
    fi
fi

# 9. Запрет уровневого middleware кроме AccessLogMiddleware: вход в request-скоуп
#    делает ровно одна точка, иначе ломается контракт enforce_required_fields.
if rg -nq 'enter_request_scope\s*\(' \
    --type py \
    --glob '!core/logging/**' \
    --glob '!core/middleware/access_log.py' \
    --glob '!core/middleware/auth/middleware.py' \
    --glob '!core/tasks/logging_middleware.py' \
    --glob '!core/utils/background.py' \
    --glob '!core/websocket/router.py' \
    --glob '!core/websocket/manager.py' \
    --glob '!apps/scheduler/dispatch.py' \
    --glob '!tests/**' \
    apps core; then
    fail "enter_request_scope(...) разрешён только в платформенных точках входа"
    rg -n 'enter_request_scope\s*\(' \
        --type py \
        --glob '!core/logging/**' \
        --glob '!core/middleware/access_log.py' \
        --glob '!core/middleware/auth/middleware.py' \
        --glob '!core/tasks/logging_middleware.py' \
        --glob '!core/utils/background.py' \
        --glob '!core/websocket/router.py' \
        --glob '!core/websocket/manager.py' \
        --glob '!apps/scheduler/dispatch.py' \
        --glob '!tests/**' \
        apps core >&2 || true
fi

# 10. clear_log_context() запрещён вне core/logging/ и core/middleware/auth/middleware.py
#     (управляет скоупом enter_request_scope/exit_request_scope, ручная очистка ломает
#     контракт обязательных полей).
if rg -nq 'clear_log_context\s*\(' \
    --type py \
    --glob '!core/logging/**' \
    --glob '!tests/**' \
    apps core; then
    fail "clear_log_context() запрещён вне core/logging — используйте exit_request_scope()"
    rg -n 'clear_log_context\s*\(' \
        --type py \
        --glob '!core/logging/**' \
        --glob '!tests/**' \
        apps core >&2 || true
fi

# 11. Прямой вызов task.kiq() без log labels: только через core.tasks.kicker.kiq_with_context
#     или task.kicker().with_labels(request_id=..., trace_id=..., service_name=...).kiq(...).
#     На переходный период жёсткого блока нет — pre_send автоматически подставляет
#     request_id/trace_id/service_name из лог-контекста (см. core/tasks/logging_middleware.py).
#     Здесь мониторим количество прямых вызовов.
KIQ_COUNT=$(rg -c '\.kiq\s*\(' apps core --type py 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
if [ "$KIQ_COUNT" -gt 0 ]; then
    echo "check_logging_canon: info — прямые .kiq(...) вызовов: $KIQ_COUNT (auto-инжектится request_id из лог-контекста; явно использовать core.tasks.kicker.kiq_with_context для документирования)" >&2
fi

if [ "$ERR" -ne 0 ]; then
    echo "check_logging_canon: FAIL" >&2
    exit 1
fi

echo "check_logging_canon: OK"
