import asyncio
import os
import time

import httpx
import pytest

# Игнорируем тест, если мы не в docker-compose (нет доступа к инфраструктуре observability)
# Проверяем наличие ENV, который задается только в tests_runner
pytestmark = pytest.mark.skipif(
    not os.getenv("TESTING") or not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    reason="Requires test environment with observability stack",
)


@pytest.mark.asyncio
async def test_observability_pipeline_e2e():
    """
    Проверяет, что:
    1. HTTP-запрос к сервису генерирует лог и трейс (через AccessLogMiddleware).
    2. Alloy забирает stdout лог из Docker сокета и отправляет в Loki-test.
    3. Приложение шлет OTLP трейс в Alloy-test, откуда он летит в Tempo-test.
    4. Grafana-test доступна.
    """
    # 1. Генерируем событие (запрос к provider_litserve)
    # Используем таймаут побольше, на случай если сервис долго стартует
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Проверяем доступность Grafana
        try:
            grafana_resp = await client.get("http://grafana-test:3000/api/health")
            assert grafana_resp.status_code == 200
        except Exception as e:
            pytest.fail(f"Grafana API недоступно: {e}")

        # Дергаем тестовый сервис
        # provider_litserve должен работать на 8014 внутри test-net
        try:
            # Делаем запрос к health endpoint (он не требует авторизации, но проходит через AccessLogMiddleware)
            resp = await client.get("http://provider_litserve:8014/litserve/health")
            assert resp.status_code == 200
        except Exception as e:
            pytest.fail(f"Не удалось достучаться до provider_litserve: {e}")

        # Вытаскиваем trace_id, который сгенерировала мидлваря платформы
        trace_id = resp.headers.get("x-trace-id")
        assert trace_id is not None, "В ответе сервиса нет заголовка X-Trace-Id!"

        # 2. Polling Loki: ждем появления лога с этим trace_id
        # У Alloy есть небольшая задержка на чтение из docker.sock и отправку
        loki_url = "http://loki-test:3100/loki/api/v1/query"
        # Экранируем кавычки для LogQL
        query = f'{{service="provider_litserve"}} | json | trace_id="{trace_id}"'
        
        log_found = False
        for _ in range(15):  # ждем до 30 секунд
            await asyncio.sleep(2.0)
            try:
                loki_resp = await client.get(loki_url, params={"query": query})
                if loki_resp.status_code == 200:
                    data = loki_resp.json()
                    results = data.get("data", {}).get("result", [])
                    if results:
                        log_found = True
                        break
            except Exception:
                pass
        
        assert log_found, f"Лог для trace_id={trace_id} не найден в Loki за 30 секунд. Alloy не перехватил stdout или не доставил."

        # 3. Polling Tempo: ждем появления трейса
        # OTel BatchSpanProcessor по умолчанию сбрасывает спаны раз в 5 секунд.
        tempo_url = f"http://tempo-test:3200/api/traces/{trace_id}"
        
        trace_found = False
        for _ in range(15):  # ждем до 30 секунд
            await asyncio.sleep(2.0)
            try:
                tempo_resp = await client.get(tempo_url)
                if tempo_resp.status_code == 200:
                    # Если вернулся 200, значит трейс существует и проиндексирован
                    trace_found = True
                    break
            except Exception:
                pass
                
        assert trace_found, f"Трейс {trace_id} не найден в Tempo за 30 секунд. OTLP -> Alloy -> Tempo пайплайн не сработал."
