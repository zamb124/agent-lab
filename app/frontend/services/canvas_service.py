"""
Сервис для работы с канвасом Flow Builder
"""

import logging
from typing import Dict, Any
from app.models import FlowConfig, ToolReference
from app.db.repositories import Storage

logger = logging.getLogger(__name__)


class CanvasService:
    """Сервис для работы с канвасом"""
    
    def __init__(self, storage: Storage):
        self.storage = storage
    
    async def update_flow_entry_point(
        self, 
        flow: FlowConfig, 
        canvas_data: Dict[str, Any]
    ):
        """
        Обновляет entry_point_agent для Flow на основе связей на канвасе
        
        Args:
            flow: Конфигурация флоу
            canvas_data: Данные канваса с нодами и связями
        """
        flow_node = None
        for node in canvas_data.get("nodes", []):
            if node.get("type") == "flow_node" and node.get("params", {}).get("flow_id") == flow.flow_id:
                flow_node = node
                break
        
        if not flow_node:
            return
        
        for edge in canvas_data.get("edges", []):
            if edge.get("source") == flow_node.get("id"):
                target_node_id = edge.get("target")
                for node in canvas_data.get("nodes", []):
                    if node.get("id") == target_node_id and node.get("type") == "agent_node":
                        agent_id = node.get("params", {}).get("agent_id")
                        if agent_id:
                            flow.entry_point_agent = agent_id
                            logger.info(f"✅ Обновлен entry_point_agent для Flow {flow.flow_id}: {agent_id}")
                            return
    
    async def update_agents_from_canvas(self, canvas_data: Dict[str, Any]):
        """
        Обновляет агентов в БД на основе связей на канвасе.
        Для ReAct агентов - обновляет tools[].
        Для StateGraph агентов - НЕ трогает graph_definition (управляется отдельно).
        
        Args:
            canvas_data: Данные канваса с нодами и связями
        """
        # Находим flow ноду для определения entry_point агента
        flow_node = None
        for node in canvas_data.get("nodes", []):
            if node.get("type") == "flow_node":
                flow_node = node
                break
        
        if not flow_node:
            logger.info("Не найдена flow нода на канвасе, пропускаем обновление агентов")
            return
        
        # Находим entry_point агента (нода связанная с flow)
        entry_point_agent_id = None
        entry_point_node_id = None
        
        for edge in canvas_data.get("edges", []):
            if edge.get("source") == flow_node.get("id"):
                target_node_id = edge.get("target")
                for node in canvas_data.get("nodes", []):
                    if node.get("id") == target_node_id and node.get("type") == "agent_node":
                        entry_point_agent_id = node.get("params", {}).get("agent_id")
                        entry_point_node_id = target_node_id
                        break
                break
        
        if not entry_point_agent_id:
            logger.info("Не найден entry_point агент, пропускаем обновление")
            return
        
        # Получаем данные entry_point агента
        entry_point_agent = await self.storage.get_agent_config(entry_point_agent_id)
        if not entry_point_agent:
            logger.warning(f"Entry point агент {entry_point_agent_id} не найден в БД")
            return
        
        # Для StateGraph агентов обновляем graph_definition из canvas
        from app.models import AgentType, GraphDefinition, GraphNode, GraphEdge
        
        if entry_point_agent.type == AgentType.STATEGRAPH:
            logger.info(f"StateGraph агент {entry_point_agent_id} - обновляем graph_definition из canvas")
            
            # Собираем ВСЕ ноды связанные с entry_point агентом рекурсивно
            graph_node_ids = set()
            
            def find_connected_nodes(node_id, visited):
                if node_id in visited:
                    return
                visited.add(node_id)
                
                for edge in canvas_data.get("edges", []):
                    if edge.get("source") == node_id:
                        target = edge.get("target")
                        if target:
                            find_connected_nodes(target, visited)
            
            # Находим все ноды начиная от entry_point агента
            find_connected_nodes(entry_point_node_id, graph_node_ids)
            logger.info(f"Найдено {len(graph_node_ids)} связанных нод: {graph_node_ids}")
            
            # Собираем ноды для graph_definition (кроме flow и entry_point agent)
            graph_nodes = []
            for node in canvas_data.get("nodes", []):
                node_id = node.get("id")
                
                # Пропускаем flow и entry_point agent ноду
                if node.get("type") == "flow_node" or node_id == entry_point_node_id:
                    logger.info(f"Пропускаем ноду {node_id} (type={node.get('type')})")
                    continue
                
                # Добавляем только ноды связанные с entry_point агентом
                if node_id in graph_node_ids:
                    node_name = node.get("params", {}).get("name") or node_id
                    logger.info(f"Добавляем ноду {node_id} (name={node_name}) в graph_definition")
                    
                    # Копируем params и добавляем UI координаты
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
                else:
                    logger.info(f"Пропускаем несвязанную ноду {node_id}")
            
            # Собираем связи для graph_definition
            graph_edges = []
            first_node_id = None
            
            for edge in canvas_data.get("edges", []):
                source = edge.get("source")
                target = edge.get("target")
                
                # Связь от entry_point агента - это START
                if source == entry_point_node_id:
                    source_node = None
                    for n in canvas_data.get("nodes", []):
                        if n.get("id") == target:
                            source_node = n
                            first_node_id = n.get("params", {}).get("name") or n.get("id")
                            break
                    
                    if first_node_id:
                        graph_edges.append(GraphEdge(
                            source="START",
                            target=first_node_id,
                            condition=None,
                            condition_type=None
                        ))
                
                # Обычные связи между нодами
                elif source in graph_node_ids and target in graph_node_ids:
                    source_node_name = None
                    target_node_name = None
                    
                    for n in canvas_data.get("nodes", []):
                        if n.get("id") == source:
                            source_node_name = n.get("params", {}).get("name") or n.get("id")
                        if n.get("id") == target:
                            target_node_name = n.get("params", {}).get("name") or n.get("id")
                    
                    if source_node_name and target_node_name:
                        edge_type = "router" if edge.get("type") == "conditional" else None
                        graph_edges.append(GraphEdge(
                            source=source_node_name,
                            target=target_node_name,
                            condition=None,
                            condition_type=edge_type
                        ))
            
            # Обновляем graph_definition
            entry_point_agent.graph_definition = GraphDefinition(
                nodes=graph_nodes,
                edges=graph_edges,
                entry_point=first_node_id or "START"
            )
            
            await self.storage.set_agent_config(entry_point_agent)
            logger.info(f"✅ Обновлено {len(graph_nodes)} нод в graph_definition StateGraph агента {entry_point_agent_id}")
            return
        
        # Для ReAct агентов - собираем tools из связей для ВСЕХ агентов на canvas
        logger.info(f"ReAct агент {entry_point_agent_id} - обновляем tools[] для всех агентов из canvas")
        
        # Собираем tools для каждого агента
        agent_tools_map = {}
        
        for edge in canvas_data.get("edges", []):
            source_id = edge.get("source")
            target_id = edge.get("target")
            
            # Находим source ноду
            source_node = None
            target_node = None
            for node in canvas_data.get("nodes", []):
                if node.get("id") == source_id:
                    source_node = node
                if node.get("id") == target_id:
                    target_node = node
            
            if not source_node or not target_node:
                continue
            
            # Если source - это agent нода
            if source_node.get("type") == "agent_node":
                agent_id = source_node.get("params", {}).get("agent_id")
                if not agent_id:
                    continue
                
                if agent_id not in agent_tools_map:
                    agent_tools_map[agent_id] = []
                
                # Добавляем tool или субагента
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
        
        # Сохраняем tools для каждого агента
        for agent_id, tools in agent_tools_map.items():
            agent = await self.storage.get_agent_config(agent_id)
            if agent:
                agent.tools = tools
                await self.storage.set_agent_config(agent)
                logger.info(f"✅ Обновлено {len(tools)} тулов для ReAct агента {agent_id}")
    
    async def save_canvas_data(
        self, 
        flow_id: str, 
        canvas_data: Dict[str, Any]
    ):
        """
        Сохранить данные канваса и обновить связанные сущности
        
        Args:
            flow_id: ID флоу
            canvas_data: Данные канваса
        """
        flow = await self.storage.get_flow_config(flow_id)
        if not flow:
            raise ValueError(f"Flow {flow_id} not found")
        
        logger.info(f"Сохраняем данные канваса для флоу {flow_id}")
        logger.info(f"Количество нод: {len(canvas_data.get('nodes', []))}")
        logger.info(f"Количество связей: {len(canvas_data.get('edges', []))}")

        await self.update_flow_entry_point(flow, canvas_data)
        
        flow.canvas_data = canvas_data
        await self.storage.set_flow_config(flow)
        
        logger.info("✅ Данные канваса сохранены в FlowConfig")
        
        await self.update_agents_from_canvas(canvas_data)
