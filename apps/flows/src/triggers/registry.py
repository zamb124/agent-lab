"""
TriggerRegistry - управление регистрацией триггеров.

Ключевой компонент:
- sync_triggers() вызывается при сохранении агента
- Находит diff между старыми и новыми триггерами
- Вызывает register/unregister для handlers
"""

from typing import Dict, Optional, Type

from apps.flows.src.models import FlowConfig, TriggerConfig, TriggerStatus, TriggerType
from apps.flows.src.triggers.handlers.base import BaseTriggerHandler
from core.logging import get_logger

logger = get_logger(__name__)


class TriggerRegistry:
    """
    Реестр и менеджер триггеров.
    
    Отвечает за:
    - Регистрацию handlers для разных типов триггеров
    - Синхронизацию триггеров при сохранении агента
    - Получение handler по типу триггера
    """
    
    def __init__(self, base_url: str):
        """
        Args:
            base_url: Базовый URL сервиса для webhook URLs
        """
        self.base_url = base_url
        self._handlers: Dict[TriggerType, BaseTriggerHandler] = {}
    
    def register_handler(
        self,
        trigger_type: TriggerType,
        handler_class: Type[BaseTriggerHandler],
    ) -> None:
        """
        Регистрирует handler для типа триггера.
        
        Args:
            trigger_type: Тип триггера
            handler_class: Класс handler
        """
        handler = handler_class(self.base_url)
        self._handlers[trigger_type] = handler
        logger.info(f"Registered trigger handler: {trigger_type.value}")
    
    def get_handler(self, trigger_type: TriggerType) -> Optional[BaseTriggerHandler]:
        """
        Получает handler по типу триггера.
        
        Args:
            trigger_type: Тип триггера
            
        Returns:
            Handler или None
        """
        return self._handlers.get(trigger_type)
    
    async def sync_triggers(
        self,
        flow_id: str,
        old_config: Optional[FlowConfig],
        new_config: FlowConfig,
    ) -> FlowConfig:
        """
        Синхронизирует триггеры при сохранении агента.
        
        Находит diff между старыми и новыми триггерами и вызывает
        register/unregister для каждого изменения.
        
        Args:
            flow_id: ID агента
            old_config: Предыдущий конфиг (None если новый агент)
            new_config: Новый конфиг
            
        Returns:
            Обновленный new_config с runtime данными триггеров
        """
        old_triggers = old_config.triggers if old_config else {}
        new_triggers = new_config.triggers
        
        old_ids = set(old_triggers.keys())
        new_ids = set(new_triggers.keys())
        
        # Триггеры для удаления
        removed_ids = old_ids - new_ids
        
        # Триггеры для добавления
        added_ids = new_ids - old_ids
        
        # Триггеры которые могли измениться
        common_ids = old_ids & new_ids
        
        # Unregister удаленных
        for trigger_id in removed_ids:
            trigger = old_triggers[trigger_id]
            await self._unregister_trigger(flow_id, trigger)
        
        # Register новых
        for trigger_id in added_ids:
            trigger = new_triggers[trigger_id]
            if trigger.enabled:
                updated_trigger = await self._register_trigger(flow_id, trigger)
                new_triggers[trigger_id] = updated_trigger
        
        # Проверяем изменения в существующих
        for trigger_id in common_ids:
            old_trigger = old_triggers[trigger_id]
            new_trigger = new_triggers[trigger_id]
            
            if self._trigger_changed(old_trigger, new_trigger):
                # Перерегистрируем
                await self._unregister_trigger(flow_id, old_trigger)
                if new_trigger.enabled:
                    updated_trigger = await self._register_trigger(flow_id, new_trigger)
                    new_triggers[trigger_id] = updated_trigger
                else:
                    # Disabled - обновляем статус
                    new_trigger.status = TriggerStatus.INACTIVE
                    new_triggers[trigger_id] = new_trigger
        
        # Обновляем конфиг
        new_config.triggers = new_triggers
        return new_config
    
    async def register_all(self, flow_id: str, config: FlowConfig) -> FlowConfig:
        """
        Регистрирует все enabled триггеры агента.
        
        Используется при старте сервиса для восстановления триггеров.
        
        Args:
            flow_id: ID агента
            config: Конфигурация агента
            
        Returns:
            Обновленный конфиг
        """
        for trigger_id, trigger in config.triggers.items():
            if trigger.enabled:
                updated_trigger = await self._register_trigger(flow_id, trigger)
                config.triggers[trigger_id] = updated_trigger
        
        return config
    
    async def unregister_all(self, flow_id: str, config: FlowConfig) -> None:
        """
        Снимает все триггеры агента.
        
        Используется при удалении агента.
        
        Args:
            flow_id: ID агента
            config: Конфигурация агента
        """
        for trigger_id, trigger in config.triggers.items():
            if trigger.status == TriggerStatus.ACTIVE:
                await self._unregister_trigger(flow_id, trigger)
    
    async def _register_trigger(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig:
        """
        Регистрирует один триггер.
        
        Args:
            flow_id: ID агента
            trigger: Конфигурация триггера
            
        Returns:
            Обновленный trigger с runtime данными
        """
        handler = self.get_handler(trigger.type)
        
        trigger_type_str = trigger.type.value if hasattr(trigger.type, 'value') else str(trigger.type)
        
        if handler is None:
            logger.warning(
                f"No handler for trigger type {trigger_type_str}, "
                f"flow_id={flow_id}, trigger={trigger.trigger_id}"
            )
            trigger.status = TriggerStatus.ERROR
            trigger.last_error = f"No handler for type {trigger_type_str}"
            return trigger
        
        try:
            updated_trigger = await handler.register(flow_id, trigger)
            logger.info(
                f"Trigger registered: flow_id={flow_id}, "
                f"trigger={trigger.trigger_id}, type={trigger_type_str}"
            )
            return updated_trigger
        except Exception as e:
            logger.error(
                f"Failed to register trigger: flow_id={flow_id}, "
                f"trigger={trigger.trigger_id}, error={e}"
            )
            trigger.status = TriggerStatus.ERROR
            trigger.last_error = str(e)
            return trigger
    
    async def _unregister_trigger(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> None:
        """
        Снимает один триггер.
        
        Args:
            flow_id: ID агента
            trigger: Конфигурация триггера
        """
        handler = self.get_handler(trigger.type)
        trigger_type_str = trigger.type.value if hasattr(trigger.type, 'value') else str(trigger.type)
        
        if handler is None:
            logger.warning(
                f"No handler for trigger type {trigger_type_str}, "
                f"cannot unregister: flow_id={flow_id}, trigger={trigger.trigger_id}"
            )
            return
        
        try:
            await handler.unregister(flow_id, trigger)
            logger.info(
                f"Trigger unregistered: flow_id={flow_id}, "
                f"trigger={trigger.trigger_id}, type={trigger_type_str}"
            )
        except Exception as e:
            logger.error(
                f"Failed to unregister trigger: flow_id={flow_id}, "
                f"trigger={trigger.trigger_id}, error={e}"
            )
    
    def _trigger_changed(
        self,
        old_trigger: TriggerConfig,
        new_trigger: TriggerConfig,
    ) -> bool:
        """
        Проверяет изменился ли триггер.
        
        Сравнивает ключевые поля, игнорируя runtime данные.
        """
        if old_trigger.enabled != new_trigger.enabled:
            return True
        
        if old_trigger.type != new_trigger.type:
            return True
        
        if old_trigger.config != new_trigger.config:
            return True
        
        if old_trigger.input_mapping != new_trigger.input_mapping:
            return True
        
        return False


__all__ = ["TriggerRegistry"]
