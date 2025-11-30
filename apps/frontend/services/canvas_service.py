"""
Сервис для работы с канвасом Flow Builder
"""

import logging
from typing import Dict, Any, Set

from apps.agents.models import (
    FlowConfig,
    ToolReference,
    AgentType,
    GraphDefinition,
    GraphNode,
    GraphEdge,
)

logger = logging.getLogger(__name__)


class CanvasService:
    """Сервис для работы с канвасом"""
    
    def __init__(self):
        self._flow_repository = None
        self._agent_repository = None
    
    @property
    def flow_repository(self):
        if self._flow_repository is None:
            from apps.frontend.container import get_frontend_container
            self._flow_repository = get_frontend_container().flow_repository
        return self._flow_repository
    
    @property
    def agent_repository(self):
        if self._agent_repository is None:
            from apps.frontend.container import get_frontend_container
            self._agent_repository = get_frontend_container().agent_repository
        return self._agent_repository
    
    async def update_flow_entry_point(self, flow: FlowConfig, canvas_data: Dict[str, Any]):
        """Обновляет entry_point_agent для Flow на основе связей на канвасе"""
        flow_node = self._find_flow_node(canvas_data, flow.flow_id)
        if not flow_node:
            return
        
        agent_id = self._find_connected_agent_id(canvas_data, flow_node.get("id"))
        if agent_id:
            flow.entry_point_agent = agent_id
            logger.info(f"Обновлен entry_point_agent для Flow {flow.flow_id}: {agent_id}")
    
    async def update_agents_from_canvas(self, canvas_data: Dict[str, Any]):
        """Обновляет агентов в БД на основе связей на канвасе"""
        flow_node = self._find_flow_node(canvas_data)
        if not flow_node:
            logger.info("Не найдена flow нода на канвасе, пропускаем обновление агентов")
            return
        
        entry_point_node_id = self._find_connected_node_id(canvas_data, flow_node.get("id"), "agent_node")
        if not entry_point_node_id:
            logger.info("Не найден entry_point агент, пропускаем обновление")
            return
        
        entry_point_agent_id = self._get_node_param(canvas_data, entry_point_node_id, "agent_id")
        if not entry_point_agent_id:
            return
        
        entry_point_agent = await self.agent_repository.get(entry_point_agent_id)
        if not entry_point_agent:
            logger.warning(f"Entry point агент {entry_point_agent_id} не найден в БД")
            return
        
        if entry_point_agent.type == AgentType.STATEGRAPH:
            await self._update_stategraph_agent(canvas_data, entry_point_agent, entry_point_node_id)
        else:
            await self._update_react_agents(canvas_data)
    
    async def save_canvas_data(self, flow_id: str, canvas_data: Dict[str, Any]):
        """Сохранить данные канваса и обновить связанные сущности"""
        flow = await self.flow_repository.get(flow_id)
        if not flow:
            raise ValueError(f"Flow {flow_id} not found")
        
        logger.info(f"Сохраняем данные канваса для флоу {flow_id}")
        logger.info(f"Количество нод: {len(canvas_data.get('nodes', []))}")
        logger.info(f"Количество связей: {len(canvas_data.get('edges', []))}")

        await self.update_flow_entry_point(flow, canvas_data)
        
        flow.canvas_data = canvas_data
        await self.flow_repository.set(flow)
        
        logger.info("Данные канваса сохранены в FlowConfig")
        
        await self.update_agents_from_canvas(canvas_data)
    
    def _find_flow_node(self, canvas_data: Dict[str, Any], flow_id: str = None) -> Dict[str, Any]:
        """Найти flow ноду в canvas_data"""
        for node in canvas_data.get("nodes", []):
            if node.get("type") != "flow_node":
                continue
            if flow_id is None or node.get("params", {}).get("flow_id") == flow_id:
                return node
        return None
    
    def _find_connected_node_id(self, canvas_data: Dict[str, Any], source_id: str, target_type: str = None) -> str:
        """Найти ID ноды связанной с source_id"""
        for edge in canvas_data.get("edges", []):
            if edge.get("source") != source_id:
                continue
            target_id = edge.get("target")
            if target_type is None:
                return target_id
            for node in canvas_data.get("nodes", []):
                if node.get("id") == target_id and node.get("type") == target_type:
                    return target_id
        return None
    
    def _find_connected_agent_id(self, canvas_data: Dict[str, Any], source_id: str) -> str:
        """Найти agent_id связанного агента"""
        node_id = self._find_connected_node_id(canvas_data, source_id, "agent_node")
        return self._get_node_param(canvas_data, node_id, "agent_id") if node_id else None
    
    def _get_node_param(self, canvas_data: Dict[str, Any], node_id: str, param: str) -> Any:
        """Получить параметр ноды по ID"""
        for node in canvas_data.get("nodes", []):
            if node.get("id") == node_id:
                return node.get("params", {}).get(param)
        return None
    
    def _get_node_by_id(self, canvas_data: Dict[str, Any], node_id: str) -> Dict[str, Any]:
        """Получить ноду по ID"""
        for node in canvas_data.get("nodes", []):
            if node.get("id") == node_id:
                return node
        return None
    
    def _find_connected_node_ids(self, canvas_data: Dict[str, Any], start_node_id: str) -> Set[str]:
        """Рекурсивно найти все связанные ноды"""
        connected = set()
        
        def traverse(node_id: str):
            if node_id in connected:
                return
            connected.add(node_id)
            for edge in canvas_data.get("edges", []):
                if edge.get("source") == node_id:
                    target = edge.get("target")
                    if target:
                        traverse(target)
        
        traverse(start_node_id)
        return connected
    
    async def _update_stategraph_agent(
        self, 
        canvas_data: Dict[str, Any], 
        agent, 
        entry_point_node_id: str
    ):
        """Обновить graph_definition для StateGraph агента"""
        logger.info(f"StateGraph агент {agent.agent_id} - обновляем graph_definition из canvas")
        
        graph_node_ids = self._find_connected_node_ids(canvas_data, entry_point_node_id)
        logger.info(f"Найдено {len(graph_node_ids)} связанных нод")
        
        graph_nodes = []
        for node in canvas_data.get("nodes", []):
            node_id = node.get("id")
            
            if node.get("type") == "flow_node" or node_id == entry_point_node_id:
                continue
            
            if node_id not in graph_node_ids:
                continue
            
            node_name = node.get("params", {}).get("name") or node_id
            node_params = node.get("params", {}).copy()
            if node.get("ui"):
                node_params["ui"] = node.get("ui")
            
            graph_nodes.append(GraphNode(
                id=node_name,
                type=node.get("type"),
                params=node_params,
                code_mode=node.get("code_mode", "code_reference"),
                inline_code=node.get("inline_code"),
                function_path=node.get("function_path")
            ))
        
        graph_edges = []
        first_node_id = None
        
        for edge in canvas_data.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            
            if source == entry_point_node_id:
                target_node = self._get_node_by_id(canvas_data, target)
                if target_node:
                    first_node_id = target_node.get("params", {}).get("name") or target
                    graph_edges.append(GraphEdge(
                        source="START",
                        target=first_node_id,
                        condition=None,
                        condition_type=None
                    ))
            elif source in graph_node_ids and target in graph_node_ids:
                source_node = self._get_node_by_id(canvas_data, source)
                target_node = self._get_node_by_id(canvas_data, target)
                
                if source_node and target_node:
                    source_name = source_node.get("params", {}).get("name") or source
                    target_name = target_node.get("params", {}).get("name") or target
                    edge_type = "router" if edge.get("type") == "conditional" else None
                    
                    graph_edges.append(GraphEdge(
                        source=source_name,
                        target=target_name,
                        condition=None,
                        condition_type=edge_type
                    ))
        
        agent.graph_definition = GraphDefinition(
            nodes=graph_nodes,
            edges=graph_edges,
            entry_point=first_node_id or "START"
        )
        
        await self.agent_repository.set(agent)
        logger.info(f"Обновлено {len(graph_nodes)} нод в graph_definition StateGraph агента {agent.agent_id}")
    
    async def _update_react_agents(self, canvas_data: Dict[str, Any]):
        """Обновить tools[] для ReAct агентов"""
        logger.info("Обновляем tools[] для всех ReAct агентов из canvas")
        
        agent_tools_map: Dict[str, list] = {}
        
        for edge in canvas_data.get("edges", []):
            source_node = self._get_node_by_id(canvas_data, edge.get("source"))
            target_node = self._get_node_by_id(canvas_data, edge.get("target"))
            
            if not source_node or not target_node:
                continue
            
            if source_node.get("type") != "agent_node":
                continue
            
            agent_id = source_node.get("params", {}).get("agent_id")
            if not agent_id:
                continue
            
            if agent_id not in agent_tools_map:
                agent_tools_map[agent_id] = []
            
            if target_node.get("type") == "tool_node":
                tool_id = target_node.get("params", {}).get("tool_id")
                if tool_id:
                    agent_tools_map[agent_id].append(ToolReference(
                        tool_id=tool_id,
                        code_mode=target_node.get("params", {}).get("code_mode", "code_reference"),
                        params={}
                    ))
            elif target_node.get("type") == "agent_node":
                sub_agent_id = target_node.get("params", {}).get("agent_id")
                if sub_agent_id:
                    agent_tools_map[agent_id].append(ToolReference(
                        tool_id=f"agent:{sub_agent_id}",
                        code_mode="code_reference",
                        params={}
                    ))
        
        for agent_id, tools in agent_tools_map.items():
            agent = await self.agent_repository.get(agent_id)
            if agent:
                agent.tools = tools
                await self.agent_repository.set(agent)
                logger.info(f"Обновлено {len(tools)} тулов для ReAct агента {agent_id}")
