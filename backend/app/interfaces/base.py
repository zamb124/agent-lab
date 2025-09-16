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

from app.core.storage import Storage
from app.core.models import TaskConfig, TaskStatus, SessionConfig, SessionStatus
from app.core.file_processor import get_default_file_processor
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


class BaseInterface(ABC):
    """
    Базовый интерфейс-адаптер для платформ.
    
    Задачи:
    1. handle() - преобразование входящих данных в Message
    2. send_message() - отправка Message обратно на платформу
    """
    
    def __init__(self, platform_config: Dict[str, Any]):
        self.platform_config = platform_config
        self.platform_name = self.__class__.__name__.replace('Interface', '').lower()
        self.storage = Storage()
    
    @abstractmethod
    async def handle_message(self, raw_data: Dict[str, Any], flow_id: str) -> Optional[Message]:
        """
        Обработка входящих данных от платформы.
        Преобразует platform-specific данные в унифицированный Message.
        """
        pass
    
    @abstractmethod
    async def send_message(self, message: Message):
        """Отправка сообщения на платформу"""
        pass
    
    async def setup_commands(self) -> bool:
        """
        Устанавливает команды для платформы.
        Базовая реализация - ничего не делает (для API не нужно).
        
        Returns:
            True если команды установлены успешно
        """
        logger.info(f"📋 Команды для {self.platform_name} не требуют установки")
        return True
    
    async def create_task(self, message: Message, flow_id: str) -> str:
        """
        Создает задачу в БД для TaskProcessor.
        Возвращает task_id.
        """
        from ..core.context import get_context
        
        storage = Storage()
        
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        # Получаем контекст из глобального состояния
        context = get_context()
        if not context:
            raise ValueError("Нет глобального контекста - проверьте AuthMiddleware")
        
        # Обогащаем контекст session_id если его нет
        if not context.session_id:
            context.session_id = message.session_id
        
        task_config = TaskConfig(
            task_id=task_id,
            flow_id=flow_id,
            context=context,  # ← Используем Context вместо отдельных полей
            status=TaskStatus.PENDING,
            input_data={
                "message": message.content,
                "metadata": message.metadata or {}
            },
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        await storage.set(f"task:{task_id}", task_config.model_dump_json())
        logger.info(f"📋 Создана задача {task_id} для flow {flow_id}")
        
        return task_id
    
    async def get_or_create_session(self, user_id: str, flow_id: str, metadata: Dict[str, Any] = None) -> str:
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
        active_session = await self._find_active_session(user_id, flow_id)
        
        if active_session:
            # Обновляем время активности
            active_session.last_activity = datetime.now(timezone.utc).isoformat()
            await self.storage.set_session_config(active_session)
            logger.info(f"📱 Используем активную сессию {active_session.session_id}")
            return active_session.session_id
        
        # Создаем новую сессию
        return await self._create_new_session(user_id, flow_id, metadata or {})
    
    async def _find_active_session(self, user_id: str, flow_id: str) -> Optional[SessionConfig]:
        """Ищет активную сессию для пользователя и flow"""
        # Ищем активные сессии для пользователя и flow
        active_sessions = await self.storage.find_active_sessions(
            platform=self.platform_name,
            user_id=user_id,
            flow_id=flow_id
        )
        
        if active_sessions:
            if len(active_sessions) > 1:
                logger.warning(f"Найдено {len(active_sessions)} активных сессий для {user_id}:{flow_id}, должна быть одна!")
            
            # Возвращаем первую найденную активную сессию
            session = active_sessions[0]
            logger.info(f"🔍 Найдена активная сессия: {session.session_id}")
            return session
        
        logger.info(f"🔍 Активных сессий не найдено для {user_id}:{flow_id}")
        return None
    
    async def _create_new_session(self, user_id: str, flow_id: str, metadata: Dict[str, Any]) -> str:
        """Создает новую сессию"""
        unique_id = uuid.uuid4().hex[:8]
        session_id = f"{self.platform_name}_{user_id}_{flow_id}_{unique_id}"
        
        session_config = SessionConfig(
            session_id=session_id,
            platform=self.platform_name,
            user_id=user_id,
            flow_id=flow_id,
            status=SessionStatus.ACTIVE,
            metadata=metadata,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_activity=datetime.now(timezone.utc).isoformat()
        )
        
        # Сохраняем в БД
        session_key = f"session:{self.platform_name}:{user_id}:{flow_id}:{unique_id}"
        await self.storage.set(session_key, session_config.model_dump_json())
        
        logger.info(f"🆕 Создана новая сессия {session_id}")
        return session_id
    
    
    async def process_command(self, content: str, user_id: str, flow_id: str) -> Tuple[bool, Optional[str]]:
        """
        Обрабатывает команды платформы.
        
        Returns:
            Tuple[is_command, response_message]
        """
        if not content.startswith('/'):
            return False, None
        
        command = content.lower().strip()
        
        if command == '/clear':
            return await self._handle_clear_command(user_id, flow_id)
        elif command == '/help':
            return await self._handle_help_command()
        elif command == '/start':
            return await self._handle_start_command()
        else:
            return True, f"Неизвестная команда: {command}\nИспользуйте /help для списка команд"
    
    async def _handle_clear_command(self, user_id: str, flow_id) -> Tuple[bool, str]:
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
    
    async def _clear_user_sessions(self, user_id: str, flow_id: str):
        """Очищает все сессии пользователя - меняет статус на INACTIVE"""
        # Находим все активные сессии пользователя
        all_sessions = await self.storage.find_active_sessions(
            platform=self.platform_name,
            user_id=user_id,
            flow_id=flow_id
        )
        
        # Меняем статус всех сессий на INACTIVE
        for session in all_sessions:
            session.status = SessionStatus.INACTIVE
            session.last_activity = datetime.now(timezone.utc).isoformat()
            await self.storage.set(session.session_key, session.model_dump_json())
            
            logger.info(f"🔒 Сессия {session.session_id} помечена как INACTIVE")
        
        logger.info(f"🧹 Все сессии пользователя {user_id} деактивированы. Следующее сообщение создаст новую сессию.")
    
    async def process_files(self, files_data: List[Dict[str, Any]], user_id: str) -> List[str]:
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
            file_record = await self._process_single_file(file_data, user_id, file_processor)
            
            if file_record:
                # Форматируем сообщение о файле
                file_message = file_processor.format_file_message(file_record)
                file_messages.append(file_message)
                logger.info(f"📎 Обработан файл: {file_record.original_name}")
        
        return file_messages
    
    async def _process_single_file(
        self, 
        file_data: Dict[str, Any], 
        user_id: str, 
        file_processor
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
        logger.warning(f"_process_single_file не реализован в {self.__class__.__name__}")
        return None
