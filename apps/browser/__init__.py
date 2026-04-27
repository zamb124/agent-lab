"""
Сервис browser: Browser Runtime v1 (Playwright + CDP).

Слои:
- `api/`: FastAPI роутеры (Browser Control HTTP API).
- `contracts/`: публичные протоколы и ошибки (stable contracts).
- `orchestration/`: сборка runtime (facade) и фабрики адаптеров.
- `engine/`: реализация runtime-движка (CDP pool, contexts, lease, lifecycle, interactor).
- `observe/`: snapshot/refs и session-scoped store для observe.
- `interaction/`: human-like действия (click/type/press) и профили.
- `adapters/`: реализации `BrowserControlAdapter` под разные backend-ы.
- `stealth/`: anti-detect init scripts и headers для BrowserContext.
"""
