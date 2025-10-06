"""
Модуль для работы с checkpointer для LangGraph.
Обеспечивает сохранение состояния агентов между вызовами.
"""

import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Глобальный checkpointer
_checkpointer = None


class CheckpointerManager:
    """Менеджер checkpointer для агентов"""

    def __init__(self):
        self._checkpointer = None

    def get_checkpointer(self, serde=None):
        """Возвращает checkpointer для агентов"""
        if serde is not None:
            # Если serde задан, создаем новый checkpointer без кэширования
            return self._create_postgres_checkpointer(serde)

        # Для стандартного случая используем кэширование
        if self._checkpointer is None:
            self._checkpointer = self._create_postgres_checkpointer()

        return self._checkpointer

    def _create_postgres_checkpointer(self, serde=None):
        """Создает checkpointer для PostgreSQL"""

        class PostgresCheckpointer:
            def __init__(self, conn_string, serde=None):
                self.conn_string = conn_string
                self.serde = serde
                self._checkpointer = None

            async def _get_checkpointer(self):
                """Создает checkpointer для операций"""
                if self.serde:
                    checkpointer_cm = AsyncPostgresSaver.from_conn_string(
                        self.conn_string, serde=self.serde
                    )
                else:
                    checkpointer_cm = AsyncPostgresSaver.from_conn_string(
                        self.conn_string
                    )

                return checkpointer_cm

            async def setup(self):
                """Создает таблицы checkpointer'а в БД"""
                checkpointer_cm = await self._get_checkpointer()
                async with checkpointer_cm as cp:
                    await cp.setup()

            async def aget_tuple(self, config):
                checkpointer_cm = await self._get_checkpointer()
                async with checkpointer_cm as cp:
                    return await cp.aget_tuple(config)

            async def aput(self, config, checkpoint, metadata, new_versions):
                checkpointer_cm = await self._get_checkpointer()
                async with checkpointer_cm as cp:
                    return await cp.aput(config, checkpoint, metadata, new_versions)

            async def alist(self, config, *, limit=None, before=None):
                checkpointer_cm = await self._get_checkpointer()
                async with checkpointer_cm as cp:
                    return cp.alist(config, limit=limit, before=before)

            async def adelete_thread(self, thread_id):
                checkpointer_cm = await self._get_checkpointer()
                async with checkpointer_cm as cp:
                    if hasattr(cp, "adelete_thread"):
                        return await cp.adelete_thread(thread_id)

            def get_next_version(self, current, channel):
                """Синхронный метод для получения следующей версии"""
                if current is None:
                    return "00000000000000000000000000000001"
                return f"{int(current.split('.')[0]) + 1:032d}"

            async def aput_writes(self, config, writes, task_id):
                """Сохранение writes"""
                checkpointer_cm = await self._get_checkpointer()
                async with checkpointer_cm as cp:
                    if hasattr(cp, "aput_writes"):
                        return await cp.aput_writes(config, writes, task_id)

            @property
            def config_specs(self):
                return []

        settings = get_settings()  # Используем синглтон
        return PostgresCheckpointer(settings.database.checkpointer_url, serde)


# Глобальный менеджер
_manager = CheckpointerManager()


async def init_checkpointer() -> None:
    """Инициализация checkpointer"""
    global _checkpointer

    try:
        logger.info("🔄 Инициализация checkpointer...")

        # Получаем checkpointer через менеджер
        checkpointer = _manager.get_checkpointer()

        if hasattr(checkpointer, "setup"):
            await checkpointer.setup()

        _checkpointer = checkpointer
        logger.info("✅ Checkpointer успешно инициализирован (PostgreSQL)")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации checkpointer: {e}")
        raise


async def get_checkpointer():
    """Получение checkpointer"""
    global _checkpointer

    if _checkpointer is None:
        await init_checkpointer()

    return _checkpointer


async def close_checkpointer() -> None:
    """Закрытие checkpointer"""
    global _checkpointer

    if _checkpointer is not None:
        try:
            # Для простых checkpointer'ов закрытие не требуется
            logger.info("✅ Checkpointer закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия checkpointer: {e}")
        finally:
            _checkpointer = None
