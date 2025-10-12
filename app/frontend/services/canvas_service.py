"""
Сервис для работы с канвасом Flow Builder
"""

import logging
from typing import Dict, Any
from app.models import FlowConfig, ToolReference
from app.core.storage import Storage

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
        Обновляет агентов в БД на основе связей на канвасе
        
        Args:
            canvas_data: Данные канваса с нодами и связями
        """
        agent_connections = {}
        
        for edge in canvas_data.get("edges", []):
            source_id = edge.get("source")
            target_id = edge.get("target")
            
            if not source_id or not target_id:
                continue
            
            source_node = None
            target_node = None
            
            for node in canvas_data.get("nodes", []):
                if node.get("id") == source_id:
                    source_node = node
                elif node.get("id") == target_id:
                    target_node = node
            
            if not source_node or not target_node:
                continue
            
            if source_node.get("type") == "agent_node":
                agent_id = source_node.get("params", {}).get("agent_id")
                if agent_id:
                    if agent_id not in agent_connections:
                        agent_connections[agent_id] = []
                    
                    if target_node.get("type") == "tool_node":
                        tool_id = target_node.get("params", {}).get("tool_id")
                        if tool_id:
                            agent_connections[agent_id].append({
                                "type": "tool",
                                "id": tool_id
                            })
                    elif target_node.get("type") == "agent_node":
                        sub_agent_id = target_node.get("params", {}).get("agent_id")
                        if sub_agent_id:
                            agent_connections[agent_id].append({
                                "type": "agent",
                                "id": sub_agent_id
                            })
        
        for agent_id, connections in agent_connections.items():
            try:
                agent = await self.storage.get_agent_config(agent_id)
                if agent:
                    new_tools = []
                    
                    for connection in connections:
                        if connection["type"] == "tool":
                            tool_ref = ToolReference(
                                tool_id=connection["id"],
                                params={}
                            )
                            new_tools.append(tool_ref)
                        elif connection["type"] == "agent":
                            agent_tool_ref = ToolReference(
                                tool_id=f"agent:{connection['id']}",
                                params={}
                            )
                            new_tools.append(agent_tool_ref)
                    
                    agent.tools = new_tools
                    await self.storage.set_agent_config(agent)
                    
            except Exception as e:
                logger.error(f"Ошибка обновления агента {agent_id}: {e}")
                continue
    
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
