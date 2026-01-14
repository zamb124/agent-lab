"""
AgentValidator - валидация структуры и ссылок в агенте.

Проверки:
1. Структура графа: entry, edges, достижимость нод
2. Ссылки: agent_id, tools, agent, remote_agent
3. Переменные: @var: в input_mapping, url, headers
4. Inline code: парсинг обращений к state
5. Попытка сборки Agent
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from apps.agents.src.agent.agent import Agent
from core.logging import get_logger

logger = get_logger(__name__)


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class AgentValidationError:
    """Ошибка валидации агента."""
    
    code: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    node_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class AgentValidationResult:
    """Результат валидации агента."""
    
    valid: bool
    errors: List[AgentValidationError] = field(default_factory=list)
    state_keys_used: Set[str] = field(default_factory=set)
    var_keys_used: Set[str] = field(default_factory=set)
    
    def add_error(
        self,
        code: str,
        message: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        node_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.errors.append(AgentValidationError(
            code=code,
            message=message,
            severity=severity,
            node_id=node_id,
            details=details,
        ))
        if severity == ValidationSeverity.ERROR:
            self.valid = False


class AgentValidator:
    """Валидатор конфигурации агента."""
    
    def __init__(
        self,
        agent_repository=None,
        tool_repository=None,
        node_repository=None,
    ):
        self.agent_repository = agent_repository
        self.tool_repository = tool_repository
        self.node_repository = node_repository
    
    async def validate(
        self,
        nodes: Dict[str, Dict[str, Any]],
        edges: List[Dict[str, Any]],
        entry: str,
        variables: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> AgentValidationResult:
        """
        Валидирует конфигурацию агента.
        
        Args:
            nodes: Словарь нод {node_id: config}
            edges: Список edges [{from, to, condition}]
            entry: ID entry ноды
            variables: Переменные агента
            agent_id: ID агента (опционально, для контекста)
            
        Returns:
            AgentValidationResult с ошибками и предупреждениями
        """
        result = AgentValidationResult(valid=True)
        
        # 1. Валидация структуры графа
        self._validate_structure(nodes, edges, entry, result)
        
        # 2. Валидация ссылок на сущности
        await self._validate_references(nodes, result)
        
        # 3. Валидация переменных @var:
        self._validate_variables(nodes, variables, result)
        
        # 4. Парсинг inline code
        self._parse_inline_code(nodes, result)
        
        # 5. Попытка сборки (если нет критических ошибок)
        if result.valid:
            await self._try_build(nodes, edges, entry, agent_id, result)
        
        return result
    
    def _validate_structure(
        self,
        nodes: Dict[str, Dict[str, Any]],
        edges: List[Dict[str, Any]],
        entry: str,
        result: AgentValidationResult,
    ):
        """Валидация структуры графа."""
        node_ids = set(nodes.keys())
        
        # Entry существует
        if not entry:
            result.add_error(
                code="missing_entry",
                message="Не указана точка входа (entry)",
            )
        elif entry not in node_ids:
            result.add_error(
                code="entry_not_found",
                message=f"Entry нода '{entry}' не найдена в nodes",
                details={"entry": entry, "available_nodes": list(node_ids)},
            )
        
        # Проверка edges
        for edge in edges:
            from_node = edge.get("from")
            to_node = edge.get("to")
            
            if from_node and from_node not in node_ids:
                result.add_error(
                    code="edge_from_not_found",
                    message=f"Edge from '{from_node}' ссылается на несуществующую ноду",
                    details={"edge": edge},
                )
            
            # to может быть null (конец графа)
            if to_node and to_node not in node_ids:
                result.add_error(
                    code="edge_to_not_found",
                    message=f"Edge to '{to_node}' ссылается на несуществующую ноду",
                    details={"edge": edge},
                )
        
        # Проверка достижимости нод от entry
        if entry and entry in node_ids:
            reachable = self._find_reachable_nodes(entry, edges, node_ids)
            unreachable = node_ids - reachable
            
            if unreachable:
                result.add_error(
                    code="unreachable_nodes",
                    message=f"Недостижимые ноды от entry: {', '.join(unreachable)}",
                    severity=ValidationSeverity.WARNING,
                    details={"unreachable": list(unreachable)},
                )
        
        # Проверка что граф имеет выход
        nodes_with_outgoing = {e.get("from") for e in edges if e.get("from")}
        terminal_nodes = node_ids - nodes_with_outgoing
        edges_to_null = [e for e in edges if e.get("to") is None]
        
        if not terminal_nodes and not edges_to_null:
            result.add_error(
                code="no_exit",
                message="Граф не имеет выхода (нет терминальных нод или edges с to=null)",
                severity=ValidationSeverity.WARNING,
            )
    
    def _validate_tool_type_uniqueness(
        self,
        node_id: str,
        tools: List[Any],
        result: AgentValidationResult,
    ):
        """Валидация что в react_node только 1 reasoning и только 1 exit tool."""
        reason_tools = []
        exit_tools = []
        
        for tool in tools:
            if isinstance(tool, dict):
                tool_type = tool.get("tool_type")
                tool_name = tool.get("tool_id") or tool.get("name", "unknown")
                
                if tool_type == "reason":
                    reason_tools.append(tool_name)
                elif tool_type == "exit":
                    exit_tools.append(tool_name)
        
        if len(reason_tools) > 1:
            result.add_error(
                code="duplicate_reason_tool",
                message=f"Только 1 reasoning tool разрешён, найдено {len(reason_tools)}: {reason_tools}",
                node_id=node_id,
            )
        
        if len(exit_tools) > 1:
            result.add_error(
                code="duplicate_exit_tool",
                message=f"Только 1 exit tool разрешён, найдено {len(exit_tools)}: {exit_tools}",
                node_id=node_id,
            )

    def _find_reachable_nodes(
        self,
        entry: str,
        edges: List[Dict[str, Any]],
        all_nodes: Set[str],
    ) -> Set[str]:
        """BFS для поиска достижимых нод от entry."""
        outgoing = {}
        for node_id in all_nodes:
            outgoing[node_id] = []
        
        for edge in edges:
            from_node = edge.get("from")
            to_node = edge.get("to")
            if from_node and to_node and from_node in outgoing:
                outgoing[from_node].append(to_node)
        
        reachable = set()
        queue = [entry]
        
        while queue:
            node = queue.pop(0)
            if node in reachable:
                continue
            reachable.add(node)
            
            for next_node in outgoing.get(node, []):
                if next_node not in reachable and next_node in all_nodes:
                    queue.append(next_node)
        
        return reachable
    
    async def _validate_references(
        self,
        nodes: Dict[str, Dict[str, Any]],
        result: AgentValidationResult,
    ):
        """Валидация ссылок на агенты, tools, agent nodes."""
        for node_id, config in nodes.items():
            node_type = config.get("type")
            if not node_type:
                result.add_error(
                    code="missing_type",
                    message=f"Node '{node_id}' requires 'type' field",
                    node_id=node_id,
                )
                continue
            
            # node_id для react_node
            if node_type == "react_node" and "node_id" in config:
                ref_node_id = config["node_id"]
                if self.node_repository:
                    node = await self.node_repository.get(ref_node_id)
                    if node is None:
                        result.add_error(
                            code="node_not_found",
                            message=f"Нода '{ref_node_id}' не найдена",
                            node_id=node_id,
                        )
            
            # tools в react_node
            tools = config.get("tools", [])
            
            # Валидация уникальности reason/exit tools
            if node_type == "react_node":
                self._validate_tool_type_uniqueness(node_id, tools, result)
            for tool_ref in tools:
                if isinstance(tool_ref, dict):
                    # Inline tool - пропускаем
                    continue
                
                # Проверяем как tool, node или agent (агенты могут использоваться как tools)
                tool_exists = False
                if self.tool_repository:
                    tool = await self.tool_repository.get(tool_ref)
                    if tool:
                        tool_exists = True
                
                if not tool_exists and self.node_repository:
                    node = await self.node_repository.get(tool_ref)
                    if node:
                        tool_exists = True
                
                if not tool_exists and self.agent_repository:
                    agent = await self.agent_repository.get(tool_ref)
                    if agent:
                        tool_exists = True
                
                if not tool_exists:
                    result.add_error(
                        code="tool_not_found",
                        message=f"Tool/Agent '{tool_ref}' не найден",
                        node_id=node_id,
                    )
            
            # tool_id для type: tool
            if node_type == "tool":
                tool_id = config.get("tool_id")
                has_code = "code" in config
                
                if tool_id and not has_code:
                    if self.tool_repository:
                        tool = await self.tool_repository.get(tool_id)
                        if tool is None:
                            result.add_error(
                                code="tool_not_found",
                                message=f"Tool '{tool_id}' не найден",
                                node_id=node_id,
                            )
            
            # agent_id для agent (ссылка на другого агента)
            if node_type == "agent":
                ref_agent_id = config.get("agent_id")
                if ref_agent_id and self.agent_repository:
                    agent = await self.agent_repository.get(ref_agent_id)
                    if agent is None:
                        result.add_error(
                            code="agent_not_found",
                            message=f"Agent '{ref_agent_id}' не найден",
                            node_id=node_id,
                        )
            
            # remote_agent
            if node_type == "remote_agent":
                agent_id = config.get("agent_id")
                url = config.get("url")
                
                if not agent_id and not url:
                    result.add_error(
                        code="remote_agent_no_target",
                        message="Remote agent должен иметь agent_id или url",
                        node_id=node_id,
                    )
    
    def _validate_variables(
        self,
        nodes: Dict[str, Dict[str, Any]],
        variables: Dict[str, Any],
        result: AgentValidationResult,
    ):
        """Валидация использования @var: переменных."""
        var_pattern = re.compile(r"@var:([a-zA-Z_][a-zA-Z0-9_.]*)")
        
        # Извлекаем имена переменных (без value обёртки)
        available_vars = set()
        for key, value in variables.items():
            available_vars.add(key)
        
        def check_var_refs(value: Any, node_id: str, context: str):
            """Рекурсивно проверяет @var: ссылки в значении."""
            if isinstance(value, str):
                for match in var_pattern.finditer(value):
                    var_name = match.group(1).split(".")[0]
                    result.var_keys_used.add(var_name)
                    
                    if var_name not in available_vars:
                        result.add_error(
                            code="undefined_variable",
                            message=f"Переменная '@var:{var_name}' не определена в секции variables",
                            severity=ValidationSeverity.ERROR,
                            node_id=node_id,
                            details={"context": context, "variable": var_name},
                        )
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_var_refs(v, node_id, f"{context}.{k}")
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    check_var_refs(v, node_id, f"{context}[{i}]")
        
        for node_id, config in nodes.items():
            # input_mapping
            if "input_mapping" in config:
                check_var_refs(config["input_mapping"], node_id, "input_mapping")
            
            # url в remote_agent и external_api
            if "url" in config:
                check_var_refs(config["url"], node_id, "url")
            
            # auth_headers
            if "auth_headers" in config:
                check_var_refs(config["auth_headers"], node_id, "auth_headers")
            
            # headers
            if "headers" in config:
                check_var_refs(config["headers"], node_id, "headers")
            
            # parameters с default
            if "parameters" in config:
                for param in config.get("parameters", []):
                    if isinstance(param, dict) and "default" in param:
                        check_var_refs(param["default"], node_id, f"parameters.{param.get('name', '?')}.default")
        
        # Проверяем значения переменных агента на @var: ссылки
        for var_key, var_value in variables.items():
            if isinstance(var_value, dict) and "value" in var_value:
                # AgentVariableConfig формат - проверяем value поле
                check_var_refs(var_value["value"], "variables", f"variables.{var_key}.value")
            elif isinstance(var_value, str):
                # Простой строковый формат
                check_var_refs(var_value, "variables", f"variables.{var_key}")
    
    def _parse_inline_code(
        self,
        nodes: Dict[str, Dict[str, Any]],
        result: AgentValidationResult,
    ):
        """Парсит inline code и извлекает обращения к state."""
        # Паттерны для обращений к state
        patterns = [
            re.compile(r"state\[(['\"])(\w+)\1\]"),  # state['key'] или state["key"]
            re.compile(r"state\.get\((['\"])(\w+)\1"),  # state.get('key')
        ]
        
        for node_id, config in nodes.items():
            code = config.get("code")
            if not code:
                continue
            
            state_keys = set()
            
            for pattern in patterns:
                for match in pattern.finditer(code):
                    key = match.group(2)
                    state_keys.add(key)
            
            if state_keys:
                result.state_keys_used.update(state_keys)
                result.add_error(
                    code="inline_code_state_keys",
                    message=f"Inline code использует state ключи: {', '.join(sorted(state_keys))}",
                    severity=ValidationSeverity.INFO,
                    node_id=node_id,
                    details={"state_keys": list(state_keys)},
                )
    
    async def _try_build(
        self,
        nodes: Dict[str, Dict[str, Any]],
        edges: List[Dict[str, Any]],
        entry: str,
        agent_id: Optional[str],
        result: AgentValidationResult,
    ):
        """Попытка собрать Agent из конфигурации."""
        try:
            config = {
                "id": agent_id or "validation_test",
                "name": "Validation Test",
                "entry": entry,
                "nodes": nodes,
                "edges": edges,
            }
            
            await Agent.from_config(config)
            
        except Exception as e:
            result.add_error(
                code="build_failed",
                message=f"Ошибка сборки Agent: {str(e)}",
                details={"exception": type(e).__name__},
            )

