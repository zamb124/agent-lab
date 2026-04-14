__all__ = ["FlowDiscoveryService", "FlowFactory", "LLMModelsService", "LaraActionEngine"]


def __getattr__(name: str):
    """Ленивый импорт для избежания circular imports."""
    if name == "FlowDiscoveryService":
        from .flow_discovery import FlowDiscoveryService

        return FlowDiscoveryService
    if name == "FlowFactory":
        from .flow_factory import FlowFactory

        return FlowFactory
    if name == "LLMModelsService":
        from .llm_models_service import LLMModelsService

        return LLMModelsService
    if name == "LaraActionEngine":
        from .lara_action_engine import LaraActionEngine

        return LaraActionEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
