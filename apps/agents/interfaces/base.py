"""
Базовый интерфейс для всех платформ.
Простые адаптеры для преобразования сообщений.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime, timezone

from apps.agents.models import TaskConfig, TaskStatus, SessionConfig, SessionStatus
from core.files.processors import (
    get_default_file_processor,
    get_default_audio_processor,
    AudioProcessor,
)
from core.context import get_context
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Унифицированное сообщение для всех платформ"""

    user_id: str
    session_id: str
    content: str
    flow_id: str
    platform: str
    metadata: Dict[str, Any] = None  # Дополнительные данные (кнопки, raw_data и т.д.)
    files: List[Dict[str, Any]] = None  # Информация о прикрепленных файлах
    context: Dict[str, Any] = None  # Контекст сообщения (импортированные сообщения и т.д.)


class BaseInterface(ABC):
    """
    Базовый интерфейс-адаптер для платформ.

    Задачи:
    1. handle() - преобразование входящих данных в Message
    2. send_message() - отправка Message обратно на платформу
    """

    def __init__(self, platform_config: Dict[str, Any]):
        self.platform_config = platform_config
        self.platform_name = self.__class__.__name__.replace("Interface", "").lower()

        container = get_agents_container()
        self.flow_repository = container.flow_repository
        self.task_repository = container.task_repository
        self.session_repository = container.session_repository

    def check_user_access(self, user_identifier: str, username: str = None) -> Tuple[bool, Optional[str]]:
        """
        Проверяет доступ пользователя к flow на основе allowed_users в platform_config.

        Args:
            user_identifier: ID пользователя (например, chat_id в Telegram)
            username: Username пользователя (например, @shvedivik без @)

        Returns:
            Tuple[allowed, error_message]: (True, None) если доступ разрешен,
                                           (False, "сообщение") если запрещен
        """
        allowed_users = self.platform_config.get("allowed_users", [])

        # Если список не задан или пустой - доступ всем
        if not allowed_users or len(allowed_users) == 0:
            return True, None

        # Проверяем user_identifier и username в списке разрешенных
        user_id_str = str(user_identifier)

        # Поддерживаем как username, так и user_id
        is_allowed = user_id_str in allowed_users or (username and username in allowed_users)

        if is_allowed:
            return True, None
        else:
            error_msg = f"❌ У вас нет доступа к этому боту.\n\nВаш идентификатор: {username or user_id_str}"
            return False, error_msg

    @abstractmethod
    async def handle_message(
        self, raw_data: Dict[str, Any], flow_id: str
    ) -> Optional[Message]:
        """
        Обработка входящих данных от платформы.
        Преобразует platform-specific данные в унифицированный Message.
        """
        pass

    @abstractmethod
    async def send_message(self, message: Message):
        """Отправка сообщения на платформу"""
        pass

    @abstractmethod
    async def send_typing_notification(self, session_id: str, is_typing: bool):
        """Отправка уведомления о печати"""
        pass

    async def start_typing_indicator(self, session_id: str):
        """
        Запускает индикатор 'печатает...'.
        Для большинства платформ - fallback к send_typing_notification(True).
        Telegram переопределяет для фоновой корутины.
        """
        await self.send_typing_notification(session_id, True)

    async def stop_typing_indicator(self, session_id: str):
        """
        Останавливает индикатор 'печатает...'.
        Для большинства платформ - fallback к send_typing_notification(False).
        Telegram переопределяет для остановки корутины.
        """
        await self.send_typing_notification(session_id, False)

    async def send_reasoning(self, session_id: str, reasoning_text: str):
        """
        Отправляет reasoning как промежуточное сообщение.
        Базовая реализация - форматирует с префиксом '💭'.
        Наследники могут переопределить для специального форматирования.

        Args:
            session_id: ID сессии
            reasoning_text: Текст reasoning от LLM
        """
        if not reasoning_text or not reasoning_text.strip():
            return

        formatted = f"💭 {reasoning_text.strip()}"

        message = Message(
            user_id="system",
            session_id=session_id,
            content=formatted,
            flow_id="system",
            platform=self.platform_name,
            metadata={"is_reasoning": True}
        )

        await self.send_message(message)
        logger.debug(f"💭 Отправлен reasoning для сессии {session_id}")

    async def send_busy_message(self, session_id: str, flow_id: str = "system"):
        """Отправляет сообщение о том что сессия занята"""
        # Для Telegram нужен chat_id в метаданных
        metadata = {"is_busy_message": True}
        if self.platform_name == "telegram":
            # Извлекаем chat_id из session_id
            if ":" in session_id:
                parts = session_id.split(":")
                if len(parts) >= 2:
                    chat_id = parts[1]  # telegram:94434940:weather_flow:xxx -> 94434940
                    metadata["chat_id"] = chat_id

        busy_message = Message(
            user_id="system",
            session_id=session_id,
            content="⏳ Подождите, обрабатываю предыдущий запрос...",
            flow_id=flow_id,
            platform=self.platform_name,
            metadata=metadata,
        )
        await self.send_message(busy_message)
        logger.info(f"⏳ Отправлено сообщение о занятости для сессии {session_id}")

    def _get_session_storage_key(self, session_id: str, flow_id: str = None) -> str:
        """Формирует ключ для хранения сессии в Storage"""
        # Если session_id уже в правильном формате platform:user:flow:id - используем как есть
        if ":" in session_id and session_id.count(":") >= 2:
            return f"session:{session_id}"

        # Иначе это простой UUID - формируем правильный формат для ЛЮБОЙ платформы
        context = get_context()
        if context and flow_id:
            # Формат: platform:user_id:flow_id:unique_id (для ВСЕХ платформ одинаково)
            full_session_id = (
                f"{self.platform_name}:{context.user.user_id}:{flow_id}:{session_id}"
            )
            return f"session:{full_session_id}"

        # Fallback если нет контекста или flow_id
        return f"session:{session_id}"

    async def setup_commands(self) -> bool:
        """
        Устанавливает команды для платформы.
        Базовая реализация - ничего не делает (для API не нужно).

        Returns:
            True если команды установлены успешно
        """
        logger.info(f"📋 Команды для {self.platform_name} не требуют установки")
        return True

    @classmethod
    async def register(
        cls,
        flow_id: str,
        username: str,
        platform_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Регистрирует/инициализирует платформу для flow.

        Базовая реализация - для платформ без специальной регистрации.
        Переопределяется в наследниках для платформ требующих настройки.

        Args:
            flow_id: ID flow
            username: Username на платформе
            platform_config: Конфигурация платформы из FlowConfig

        Returns:
            Результат регистрации
        """
        platform_name = cls.__name__.replace("Interface", "").lower()
        logger.info(f"📋 Платформа {platform_name} не требует регистрации")
        return {
            "success": True,
            "platform": platform_name,
            "mode": "direct",
            "registered": False
        }

    async def create_task(self, message: Message, flow_id: str) -> str:
        """
        Создает задачу в БД для TaskProcessor.
        Возвращает task_id.
        """

        logger.info(f"🔄 create_task вызван для session_id={message.session_id}")

        storage = get_agents_container().storage

        # Получаем правильный ключ сессии с учетом flow_id
        session_key = self._get_session_storage_key(message.session_id, flow_id)
        logger.info(f"🔍 Ищем сессию по ключу: {session_key}")
        session_data = await storage.get(session_key)
        logger.info(f"🔍 Данные сессии найдены: {bool(session_data)}")

        if session_data:
            # Проверяем что это действительно SessionConfig
            import json
            data = json.loads(session_data)
            if not isinstance(data, dict) or not all(field in data for field in ['session_id', 'platform', 'user_id']):
                logger.warning(f"Данные в {session_key} не являются SessionConfig")
                session_data = None

        if session_data:
            session_config = SessionConfig.model_validate_json(session_data)
            logger.info(f"🔍 Текущий статус сессии: {session_config.status}")

            if session_config.status == SessionStatus.PROCESSING:
                # Ищем pending задачу для этой сессии
                pending_task = await storage.find_pending_task(message.session_id, flow_id)

                if pending_task:
                    # Приклеиваем сообщение к существующей pending задаче
                    logger.info(f"🔄 Найдена pending задача {pending_task.task_id}, приклеиваем сообщение")

                    old_message = pending_task.input_data.get("message", "")
                    new_message = f"{old_message} | {message.content}"
                    pending_task.input_data["message"] = new_message
                    pending_task.input_data["message_count"] = pending_task.input_data.get("message_count", 1) + 1

                    await self.task_repository.set(pending_task)
                    logger.info(f"✅ Приклеили сообщение к задаче {pending_task.task_id}")
                    return pending_task.task_id
                else:
                    # Нет pending задачи - создаем новую
                    logger.info(f"🆕 Нет pending задачи, создаем новую для {message.session_id}")
            elif session_config.status == SessionStatus.WAITING_INPUT:
                # Сессия ждет ответ на interrupt - это нормально, продолжаем
                logger.info(
                    f"🔄 Сессия {message.session_id} в статусе WAITING_INPUT - принимаем ответ"
                )

            # Обновляем только last_activity, статус не меняем если уже PROCESSING
            if session_config.status != SessionStatus.PROCESSING:
                session_config.status = SessionStatus.PROCESSING
                logger.info(f"🔄 Сессия {message.session_id} переведена в статус PROCESSING")
            session_config.last_activity = datetime.now(timezone.utc)
            session_dict = session_config.model_dump(mode='json')
            await storage.set(session_key, json.dumps(session_dict, default=str))
        else:
            # Создаем новую сессию в БД
            logger.info(f"🆕 Создаем новую сессию в БД: {message.session_id}")
            session_config = SessionConfig(
                session_id=message.session_id,
                platform=message.platform,
                user_id=message.user_id,
                flow_id=flow_id,
                status=SessionStatus.PROCESSING,
                metadata=message.metadata or {},
                created_at=datetime.now(timezone.utc),
                last_activity=datetime.now(timezone.utc),
            )
            import json
            session_dict = session_config.model_dump(mode='json')
            await storage.set(session_key, json.dumps(session_dict, default=str))
            logger.info(f"✅ Новая сессия {message.session_id} создана в БД")

        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # Получаем контекст из глобального состояния
        context = get_context()
        if not context:
            raise ValueError("Нет глобального контекста - проверьте AuthMiddleware")

        # Логируем компанию при создании задачи
        company_id = context.active_company.company_id if context.active_company else 'НЕТ'
        logger.info(f"🔍 Создаем задачу в контексте: company={company_id}, user={context.user.user_id if context.user else 'НЕТ'}")

        # Обогащаем контекст session_id если его нет
        context.session_id = message.session_id or context.session_id

        # Загружаем и добавляем flow_config в контекст
        flow_config = await self.flow_repository.get(flow_id)
        if flow_config:
            context.flow_config = flow_config
            logger.debug(f"Flow config добавлен в контекст: {flow_id}")

        # Добавляем импортированные сообщения в context.state.messages если есть
        if context.state is None:
            context.state = {}

        # Получаем импортированные сообщения из context сообщения
        imported_messages = []
        if message.context and "imported_messages" in message.context:
            imported_messages = message.context["imported_messages"]

            # Инициализируем messages если нет
            if "messages" not in context.state:
                context.state["messages"] = []

            # Мержим сообщения по external_id чтобы избежать дублирования
            existing_messages = context.state["messages"]
            existing_external_ids = {msg.get("external_id") for msg in existing_messages if msg.get("external_id")}

            # Добавляем только новые сообщения
            new_messages = []
            for msg in imported_messages:
                if msg.get("external_id") not in existing_external_ids:
                    new_messages.append(msg)
                    existing_external_ids.add(msg.get("external_id"))

            # Добавляем новые сообщения в начало истории
            context.state["messages"] = new_messages + existing_messages
            logger.info(f"📚 Добавлено {len(new_messages)} новых сообщений из {len(imported_messages)} импортированных в context.state.messages")

        task_config = TaskConfig(
            task_id=task_id,
            flow_id=flow_id,
            context=context,
            status=TaskStatus.PENDING,
            input_data={"message": message.content, "metadata": message.metadata or {}},
            created_at=datetime.now(timezone.utc),
        )

        task_key = f"task:{task_id}"
        logger.info(f"📋 Создаем задачу {task_id} для flow {flow_id}")
        logger.info(f"  - Исходный ключ: {task_key}")
        logger.info(f"  - Статус: {task_config.status}")
        logger.info(f"  - Компания в контексте: {company_id}")

        logger.info(f"🔵 ПЕРЕД storage.set: key={task_key}")
        await storage.set(task_key, task_config.model_dump_json(), force_global=True)
        logger.info(f"🟢 ПОСЛЕ storage.set: key={task_key}")

        # Проверяем что задача реально сохранилась
        saved_task = await storage.get(task_key, force_global=True)
        if saved_task:
            logger.info(f"✅ Задача {task_id} сохранена и проверена в БД")
        else:
            logger.error(f"❌ Задача {task_id} НЕ найдена после сохранения!")

        logger.info(f"📋 Создана задача {task_id} для flow {flow_id}")

        return task_id

    async def get_or_create_session(
        self, user_id: str, flow_id: str, metadata: Dict[str, Any] = None
    ) -> str:
        """
        Получает активную сессию или создает новую.

        Args:
            user_id: ID пользователя
            flow_id: ID flow для сессии
            metadata: Дополнительные данные (chat_id, etc.)

        Returns:
            session_id для использования в задачах
        """
        # Ищем активную сессию для пользователя и flow
        logger.info(
            f"🔍 Ищем активную сессию для user_id={user_id}, flow_id={flow_id}, platform={self.platform_name}"
        )
        active_session = await self._find_active_session(user_id, flow_id)

        if active_session:
            # Обновляем время активности
            active_session.last_activity = datetime.now(timezone.utc).isoformat()
            await self.session_repository.set(active_session)
            logger.info(f"📱 Используем активную сессию {active_session.session_id}")
            return active_session.session_id

        # Создаем новую сессию
        return await self._create_new_session(user_id, flow_id, metadata or {})

    async def get_session(self, session_id: str) -> Optional[SessionConfig]:
        """Получает сессию по session_id"""
        return await self.session_repository.get(session_id)

    async def _find_active_session(
        self, user_id: str, flow_id: str
    ) -> Optional[SessionConfig]:
        """Ищет активную сессию для пользователя и flow"""
        # Ищем активные сессии для пользователя и flow
        active_sessions = await self.session_repository.find_active(
            platform=self.platform_name, user_id=user_id, flow_id=flow_id
        )

        if active_sessions:
            if len(active_sessions) > 1:
                logger.warning(
                    f"Найдено {len(active_sessions)} активных сессий для {user_id}:{flow_id}, должна быть одна!"
                )

            # Возвращаем первую найденную активную сессию
            session = active_sessions[0]
            logger.info(f"🔍 Найдена активная сессия: {session.session_id}")
            return session

        logger.info(f"🔍 Активных сессий не найдено для {user_id}:{flow_id}")
        return None

    async def _create_new_session(
        self, user_id: str, flow_id: str, metadata: Dict[str, Any]
    ) -> str:
        """Создает новую сессию"""
        unique_id = uuid.uuid4().hex[:8]
        session_id = f"{self.platform_name}:{user_id}:{flow_id}:{unique_id}"

        session_config = SessionConfig(
            session_id=session_id,
            platform=self.platform_name,
            user_id=user_id,
            flow_id=flow_id,
            status=SessionStatus.ACTIVE,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc).isoformat(),
        )

        # Сохраняем в БД через единый метод
        await self.session_repository.set(session_config)

        logger.info(f"🆕 Создана новая сессия {session_id}")
        return session_id

    async def process_command(
        self, content: str, user_id: str, flow_id: str, session_id: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Обрабатывает команды платформы.

        Returns:
            Tuple[is_command, response_message]
        """
        if not content.startswith("/"):
            return False, None

        command = content.lower().strip()

        if command == "/clear":
            return await self._handle_clear_command(user_id, flow_id, session_id)
        elif command == "/help":
            return await self._handle_help_command()
        elif command == "/start":
            return await self._handle_start_command()
        else:
            return (
                True,
                f"Неизвестная команда: {command}\nИспользуйте /help для списка команд",
            )

    async def _handle_clear_command(
        self, user_id: str, flow_id: str, session_id: str = None
    ) -> Tuple[bool, str]:
        """Очищает все сессии пользователя"""
        try:
            # Очищаем checkpointer для всех сессий пользователя
            await self._clear_user_sessions(user_id, flow_id)

            return True, "🧹 Контекст диалога очищен! Начинаем новый разговор."
        except Exception as e:
            logger.error(f"Ошибка очистки сессий для {user_id}: {e}")
            return True, "❌ Ошибка очистки контекста"

    async def _handle_help_command(self) -> Tuple[bool, str]:
        """Показывает список команд"""
        help_text = """
🤖 **Доступные команды:**

/clear - Очистить контекст диалога
/help - Показать эту справку
/start - Начать новый диалог

Просто напишите сообщение для общения с ИИ агентом!
        """.strip()
        return True, help_text

    async def _handle_start_command(self) -> Tuple[bool, str]:
        """Приветствие"""
        return True, "👋 Привет! Я ИИ агент. Чем могу помочь?"

    async def _handle_unlock_command(
        self, user_id: str, flow_id: str, session_id: str = None
    ) -> Tuple[bool, str]:
        """Принудительно разблокирует сессию"""

        if not session_id:
            return True, "Не удалось определить сессию для разблокировки"

        session_config = await self.session_repository.get(session_id)

        if not session_config:
            return True, "Сессия не найдена"

        session_config.status = SessionStatus.ACTIVE
        session_config.last_activity = datetime.now(timezone.utc)
        await self.session_repository.set(session_config)
        return True, "Сессия разблокирована! Можете продолжать общение."

    async def _clear_user_sessions(self, user_id: str, flow_id: str):
        """Очищает все сессии пользователя - меняет статус на INACTIVE"""
        logger.info(
            f"🔍 Ищем сессии для очистки: platform={self.platform_name}, user_id={user_id}, flow_id={flow_id}"
        )

        # Находим все активные сессии пользователя
        all_sessions = await self.session_repository.find_active(
            platform=self.platform_name, user_id=user_id, flow_id=flow_id
        )

        logger.info(f"🔍 Найдено {len(all_sessions)} активных сессий для очистки")

        for session in all_sessions:
            session.status = SessionStatus.INACTIVE
            session.last_activity = datetime.now(timezone.utc).isoformat()
            await self.session_repository.set(session)

            logger.info(f"Сессия {session.session_id} помечена как INACTIVE")

        logger.info(
            f"🧹 Все сессии пользователя {user_id} деактивированы. Следующее сообщение создаст новую сессию."
        )

    async def process_files(
        self, files_data: List[Dict[str, Any]], user_id: str
    ) -> List[str]:
        """
        Обрабатывает прикрепленные файлы.

        Args:
            files_data: Список данных о файлах от платформы
            user_id: ID пользователя

        Returns:
            Список отформатированных сообщений о файлах
        """
        if not files_data:
            return []

        file_processor = await get_default_file_processor()
        file_messages = []

        for file_data in files_data:
            # Обрабатываем файл (должно быть переопределено в наследниках)
            file_record = await self._process_single_file(
                file_data, user_id, file_processor
            )

            if file_record:
                # Форматируем сообщение о файле
                file_message = file_processor.format_file_message(file_record)
                file_messages.append(file_message)
                logger.info(f"📎 Обработан файл: {file_record.original_name}")

        return file_messages

    async def _process_single_file(
        self, file_data: Dict[str, Any], user_id: str, file_processor
    ):
        """
        Обрабатывает один файл. Должно быть переопределено в наследниках.

        Args:
            file_data: Данные о файле от платформы
            user_id: ID пользователя
            file_processor: Экземпляр файлового процессора

        Returns:
            FileRecord или None
        """
        # Базовая реализация - ничего не делает
        logger.warning(
            f"_process_single_file не реализован в {self.__class__.__name__}"
        )
        return None

    async def process_audio_files(
        self, audio_files_data: List[Dict[str, Any]], user_id: str
    ) -> List[str]:
        """
        Обрабатывает аудиофайлы через AudioProcessor с автоматическим распознаванием речи.

        Args:
            audio_files_data: Список данных об аудиофайлах от платформы
            user_id: ID пользователя

        Returns:
            Список отформатированных сообщений об аудиофайлах
        """
        if not audio_files_data:
            return []

        audio_processor = await get_default_audio_processor()
        audio_messages = []

        for audio_data in audio_files_data:
            # Обрабатываем аудиофайл (должно быть переопределено в наследниках)
            audio_record = await self._process_single_audio_file(
                audio_data, user_id, audio_processor
            )

            if audio_record:
                # Форматируем сообщение об аудиофайле
                audio_message = audio_processor.format_audio_message(audio_record)
                audio_messages.append(audio_message)
                logger.info(f"🎵 Обработан аудиофайл: {audio_record.original_name}")

        return audio_messages

    async def _process_single_audio_file(
        self, audio_data: Dict[str, Any], user_id: str, audio_processor
    ):
        """
        Обрабатывает один аудиофайл. Должно быть переопределено в наследниках.

        Args:
            audio_data: Данные об аудиофайле от платформы
            user_id: ID пользователя
            audio_processor: Экземпляр аудио процессора

        Returns:
            AudioRecord или None
        """
        # Базовая реализация - ничего не делает
        logger.warning(
            f"_process_single_audio_file не реализован в {self.__class__.__name__}"
        )
        return None

    def extract_outgoing_audio_from_message(self, message_content: str) -> tuple[str, List[Dict[str, Any]]]:
        """
        Извлекает [AUDIO] блоки из исходящего сообщения агента.

        Args:
            message_content: Содержимое сообщения от агента

        Returns:
            (текст_без_аудио, список_аудиофайлов)
        """


        # Извлекаем аудио блоки
        audio_files = AudioProcessor.extract_audio_info_from_message(message_content)

        if not audio_files:
            return message_content, []

        # Удаляем [AUDIO] блоки из текста сообщения
        import re
        pattern = r"\[AUDIO\].*?\[/AUDIO\]"
        clean_text = re.sub(pattern, "", message_content, flags=re.DOTALL).strip()

        return clean_text, audio_files
