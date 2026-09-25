from typing import TypeAlias

from apps.flows.src.models import FlowToolReference, NodeConfig, ToolReference
from core.types import JsonObject

ToolMaterializeInput: TypeAlias = FlowToolReference | ToolReference | NodeConfig | JsonObject
