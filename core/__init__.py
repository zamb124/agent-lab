"""
Core - общая инфраструктура Humanitec.

Независимый модуль, который НЕ зависит от apps/.
Содержит базовые компоненты для всех сервисов платформы.

Структура:
- config/       - Конфигурация (каскадная загрузка)
- db/           - База данных (Storage, BaseRepository)
- models/       - Базовые модели (User, Company, Context)
- context/      - Глобальный контекст (contextvars)
- http/         - HTTP клиенты с прокси
- logging/      - Логирование (JSON, Structured)
- container/    - DI контейнер (BaseContainer)
- variables/    - Переменные компаний (резолюция @var:key)
- files/        - Файлы и S3 (FilesService, S3Client)
- clients/      - Клиенты (LLM, NanoBanana, STT, Payment)
- utils/        - Утилиты (tokens, slug)
- middleware/   - Middleware
- identity/     - Идентификация
- i18n/         - Интернационализация
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
