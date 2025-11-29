"""
ReActAgent - реактивный агент на базе ReAct паттерна.
Использует ReactAgentRunner для выполнения ReAct цикла.
"""

import logging

from apps.agents.agents.base import BaseAgent
from core.clients.llm import get_llm
from apps.agents.services.agent_runner import ReactAgentRunner

logger = logging.getLogger(__name__)


class ReActAgent(BaseAgent):
    """
    Реактивный агент на базе ReAct паттерна.
    
    Использует ReactAgentRunner для выполнения ReAct цикла.
    Требует наличия prompt в конфигурации.
    Поддерживает динамические переменные в промпте.
    """

    async def get_runner(self):
        """
        Создает ReactAgentRunner для выполнения агента.
        
        Returns:
            ReactAgentRunner для выполнения ReAct цикла
            
        Raises:
            ValueError: Если не указан prompt в конфигурации
        """
        if not self.config.prompt:
            raise ValueError(f"ReAct агент {self.config.agent_id} требует prompt")
        
        llm = self._get_llm()
        tools = await self.get_tools()
        logger.info(f"🔧 ReactAgent.get_runner: загружено {len(tools)} tools для агента {self.config.agent_id}")
        if tools:
            tool_names = [getattr(t, 'name', str(t)) for t in tools]
            logger.info(f"🔧 ReactAgent.get_runner: tools={tool_names}")
        prompt = self.config.prompt
        
        return ReactAgentRunner(
            agent_config=self.config,
            tools=tools,
            llm=llm,
            prompt=prompt
        )

    def _get_llm(self):
        """
        Получает LLM на основе конфигурации агента.
        
        Returns:
            Экземпляр LLM с настройками из config.llm_config
        """
        if self.config.llm_config:
            llm_kwargs = {}
            if self.config.llm_config.temperature is not None:
                llm_kwargs["temperature"] = self.config.llm_config.temperature
            if self.config.llm_config.max_tokens is not None:
                llm_kwargs["max_tokens"] = self.config.llm_config.max_tokens

            return get_llm(
                model_name=self.config.llm_config.model,
                temperature=llm_kwargs.get("temperature"),
            )
        else:
            return get_llm()

