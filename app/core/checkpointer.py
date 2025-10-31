"""
Модуль для работы с checkpointer для LangGraph.
Обеспечивает сохранение состояния агентов между вызовами.
"""

import asyncio
import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings
from app.core.tracing.decorators import trace_span
from app.models.trace_models import SpanType

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
                logger.info(f"🔍 checkpointer.aget_tuple: config={config}")
                result = await cp.aget_tuple(config)
                logger.info(f"🔍 checkpointer.aget_tuple: result={result}")
                return result

            async def aput(self, config, checkpoint, metadata, new_versions):
                cp = await self._get_connection()
                logger.info(f"🔍 checkpointer.aput: config={config}, checkpoint keys={list(checkpoint.keys()) if isinstance(checkpoint, dict) else 'not dict'}")
                result = await cp.aput(config, checkpoint, metadata, new_versions)
                logger.info(f"🔍 checkpointer.aput: result={result}")
                return result

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


@trace_span(
    name="checkpointer.init_checkpointer",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "init"}
)
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


@trace_span(
    name="checkpointer.get_checkpointer",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "get"}
)
async def get_checkpointer():
    """Получение checkpointer"""
    global _checkpointer

    if _checkpointer is None:
        await init_checkpointer()

    logger.info(f"🔍 get_checkpointer: возвращаем checkpointer {type(_checkpointer)}")
    return _checkpointer


@trace_span(
    name="checkpointer.update_checkpointer_with_store_changes",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "update_store"}
)
async def update_checkpointer_with_store_changes(checkpointer, run_config: dict, store_data: dict):
    """
    Обновляет checkpointer с изменениями store, сделанными в tools.
    Это лаконичная архитектура для персистентности state.
    """
    # Получаем текущий checkpoint
    checkpoint_tuple = await checkpointer.aget_tuple(run_config)
    if checkpoint_tuple and checkpoint_tuple.checkpoint:
        # Обновляем channel_values с новыми данными store
        updated_channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
        updated_channel_values["store"] = store_data

        # Создаем новый checkpoint с обновленными данными
        updated_checkpoint = checkpoint_tuple.checkpoint.copy()
        updated_checkpoint["channel_values"] = updated_channel_values

        # Обновляем channel_versions для store
        channel_versions = checkpoint_tuple.checkpoint.get("channel_versions", {})
        if "store" in channel_versions:
            # Инкрементируем версию store
            current_version = channel_versions["store"]
            if isinstance(current_version, str):
                try:
                    new_version = f"{int(current_version.split('.')[0]) + 1:032d}"
                except:
                    new_version = "00000000000000000000000000000002"
            else:
                new_version = "00000000000000000000000000000002"
            channel_versions["store"] = new_version
        else:
            channel_versions["store"] = "00000000000000000000000000000001"

        # Сохраняем обновленный checkpoint
        # Используем checkpoint_tuple.config для сохранения (содержит checkpoint_ns)
        await checkpointer.aput(
            checkpoint_tuple.config,
            updated_checkpoint,
            checkpoint_tuple.metadata,
            channel_versions
        )

        logger.info(f"✅ Store обновлен в checkpointer: {list(store_data.keys())}")
    else:
        logger.warning("⚠️ Не удалось получить checkpoint для обновления store")


@trace_span(
    name="checkpointer.close_checkpointer",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "close_global"}
)
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
