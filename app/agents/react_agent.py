"""
ReActAgent - реактивный агент на базе ReAct паттерна.
Использует create_react_agent из LangGraph для создания графа.
"""

import logging
from typing import Any, Dict, Optional

from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import Runnable

from app.agents.base import BaseAgent
from app.core.llm_factory import get_llm
from app.core.checkpointer import get_checkpointer
from app.core.state import State
from app.core.variables import VariableResolver
from app.core.state_modifier import render_state_variables

logger = logging.getLogger(__name__)


class ReActAgent(BaseAgent):
    """
    Реактивный агент на базе ReAct паттерна.
    
    Использует встроенный create_react_agent из LangGraph.
    Требует наличия prompt в конфигурации.
    Поддерживает динамические переменные в промпте.
    """

    async def compile_graph(self) -> Runnable:
        """
        Компилирует ReAct граф на основе конфигурации.
        Использует кэширование для повторных вызовов.
        
        Returns:
            Скомпилированный граф LangGraph
            
        Raises:
            ValueError: Если не указан prompt в конфигурации
        """
        if self._compiled_graph is not None:
            logger.debug(f"Используем кэшированный граф для {self.config.agent_id}")
            return self._compiled_graph
            
        logger.info(f"Компиляция ReAct графа для агента: {self.config.agent_id}")
        
        if not self.config.prompt:
            raise ValueError(f"ReAct агент {self.config.agent_id} требует prompt")

        llm = self._get_llm()
        tools = await self.get_tools()
        dynamic_prompt = self._create_dynamic_prompt()
        checkpointer = await get_checkpointer()

        graph = create_react_agent(
            model=llm,
            tools=tools,
            prompt=dynamic_prompt,
            checkpointer=checkpointer,
            state_schema=State
        )

        self._compiled_graph = graph
        logger.info(f"ReAct граф создан для агента {self.config.agent_id}")
        return graph

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
                model=self.config.llm_config.model,
                **llm_kwargs,
            )
        else:
            return get_llm()

    def _create_dynamic_prompt(self):
        """
        Создает динамический prompt с поддержкой переменных.
        
        ЭТАП 1: Рендерит статические переменные (company_name, current_date и т.д.)
        ЭТАП 2: Создает функцию для динамических переменных из state
        
        Returns:
            Функция, которая принимает State и возвращает отрендеренный prompt
        """
        local_vars = self.config.local_variables if hasattr(self.config, 'local_variables') else {}
        static_rendered_prompt = VariableResolver.render_template(
            self.config.prompt,
            local_vars=local_vars,
            include_system=False
        )
        logger.info(f"Статические переменные подставлены для {self.config.agent_id}")

        def dynamic_prompt(state: State) -> list:
            """
            Динамический промпт, который рендерится перед каждым вызовом LLM.
            
            Args:
                state: Текущее состояние графа
                
            Returns:
                Список сообщений: system message + история из state
            """
            context = {
                "store": state.get("store", {}),
                "user_id": state.get("user_id", ""),
                "session_id": state.get("session_id", ""),
                "task_id": state.get("task_id", ""),
                "remaining_steps": state.get("remaining_steps", 0),
            }
            
            store = state.get("store", {})
            if isinstance(store, dict):
                for key, value in store.items():
                    if key not in context:
                        context[key] = value
            
            # Добавляем системные переменные на каждом шаге (актуальное время/дата)
            sys_vars = VariableResolver.resolve_all(include_system=True)

            combined_context = dict(sys_vars)
            combined_context.update(context)

            rendered = render_state_variables(
                static_rendered_prompt,
                context=combined_context,
                full_state=state
            )
            
            return [{"role": "system", "content": rendered}] + state.get("messages", [])
        
        logger.info(f"Dynamic prompt создан для {self.config.agent_id}")
        return dynamic_prompt

