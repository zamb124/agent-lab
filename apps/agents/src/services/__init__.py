__all__ = ["AgentDiscoveryService", "AgentFactory", "LLMModelsService"]


def __getattr__(name: str):
    """Ленивый импорт для избежания circular imports."""
    if name == "AgentDiscoveryService":
        from .agent_discovery import AgentDiscoveryService

        return AgentDiscoveryService
    if name == "AgentFactory":
        from .agent_factory import AgentFactory

        return AgentFactory
    if name == "LLMModelsService":
        from .llm_models_service import LLMModelsService

        return LLMModelsService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
