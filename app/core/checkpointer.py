"""
Модуль для работы с checkpointer для LangGraph.
Обеспечивает сохранение состояния агентов между вызовами.
"""

import asyncio
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
                self._connection = None
                self._context_manager = None
                self._lock = asyncio.Lock()

            async def _get_connection(self):
                """Получает или создает переиспользуемое соединение"""
                async with self._lock:
                    # Проверяем что соединение существует и активно
                    if self._connection is not None:
                        # Проверяем статус соединения
                        try:
                            if hasattr(self._connection, 'conn') and hasattr(self._connection.conn, 'closed'):
                                if self._connection.conn.closed:
                                    logger.debug("⚠️ Соединение закрыто, пересоздаем...")
                                    self._connection = None
                                    self._context_manager = None
                        except:
                            # Если проверка не удалась, пересоздадим соединение
                            self._connection = None
                            self._context_manager = None
                    
                    if self._connection is None:
                        if self.serde:
                            self._context_manager = AsyncPostgresSaver.from_conn_string(
                                self.conn_string, serde=self.serde
                            )
                        else:
                            self._context_manager = AsyncPostgresSaver.from_conn_string(
                                self.conn_string
                            )
                        
                        self._connection = await self._context_manager.__aenter__()
                        logger.debug("✅ Создано переиспользуемое соединение с PostgreSQL checkpointer")
                    
                    return self._connection

            async def setup(self):
                """Создает таблицы checkpointer'а в БД"""
                cp = await self._get_connection()
                await cp.setup()

            async def aget_tuple(self, config):
                cp = await self._get_connection()
                return await cp.aget_tuple(config)

            async def aput(self, config, checkpoint, metadata, new_versions):
                cp = await self._get_connection()
                return await cp.aput(config, checkpoint, metadata, new_versions)

            async def alist(self, config, *, limit=None, before=None):
                cp = await self._get_connection()
                return cp.alist(config, limit=limit, before=before)

            async def adelete_thread(self, thread_id):
                cp = await self._get_connection()
                if hasattr(cp, "adelete_thread"):
                    return await cp.adelete_thread(thread_id)

            def get_next_version(self, current, channel):
                """Синхронный метод для получения следующей версии"""
                if current is None:
                    return "00000000000000000000000000000001"
                return f"{int(current.split('.')[0]) + 1:032d}"

            async def aput_writes(self, config, writes, task_id):
                """Сохранение writes"""
                cp = await self._get_connection()
                if hasattr(cp, "aput_writes"):
                    return await cp.aput_writes(config, writes, task_id)

            async def close(self):
                """Закрывает соединение"""
                async with self._lock:
                    if self._connection is not None and self._context_manager is not None:
                        try:
                            await self._context_manager.__aexit__(None, None, None)
                            logger.info("✅ PostgreSQL checkpointer connection закрыт")
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка при закрытии checkpointer connection: {e}")
                        finally:
                            self._connection = None
                            self._context_manager = None

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
            if hasattr(_checkpointer, 'close'):
                await _checkpointer.close()
            logger.info("✅ Checkpointer закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия checkpointer: {e}")
        finally:
            _checkpointer = None
