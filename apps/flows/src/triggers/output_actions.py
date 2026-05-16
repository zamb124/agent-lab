"""Post-flow output actions for trigger executions."""

from __future__ import annotations

from typing import Any

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.mapping import MappingResolver
from apps.flows.src.models.channel_config import OutputAction
from apps.flows.src.triggers.input_mapper import InputMapper
from apps.flows.src.triggers.output_condition import evaluate_output_action_condition
from core.logging import get_logger

logger = get_logger(__name__)


class OutputActionExecutor:
    """
    Выполняет output_actions после успешного завершения flow без interrupt/breakpoint.
    """

    def __init__(self, *, container: FlowRuntimeContainer):
        self.container = container
        self._input_mapper = InputMapper()

    async def execute(
        self,
        output_actions: list[OutputAction],
        state: dict[str, Any],
        trigger_config: dict[str, Any],
        original_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not output_actions:
            return []

        results = []
        variables = state.get("variables", {})

        for action in output_actions:
            if action.condition:
                if not evaluate_output_action_condition(action.condition, state):
                    logger.debug(
                        f"Output action {action.action} skipped: condition not met"
                    )
                    continue

            params = self._resolve_mapping(action.mapping, state, original_payload)
            params.update(action.config)

            handler = self.container.channel_registry.get(action.channel)
            channel_config = {**trigger_config, **action.config}

            try:
                result = await handler.execute_action(
                    action=action.action,
                    params=params,
                    config=channel_config,
                    variables=variables,
                )
                ch_label = (
                    action.channel.value
                    if hasattr(action.channel, "value")
                    else str(action.channel)
                )
                logger.info(f"Output action {ch_label}:{action.action} executed")
                results.append({"action": action.action, "result": result})
            except Exception as e:
                logger.error(f"Output action {action.action} failed: {e}")
                results.append({"action": action.action, "error": str(e)})

        return results

    def _resolve_mapping(
        self,
        mapping: dict[str, str],
        state: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = {}

        for param_name, expr in mapping.items():
            if expr.startswith("@state:") or expr.startswith("@var:"):
                result[param_name] = MappingResolver.resolve_value(expr, state)
            elif expr.startswith("@trigger:"):
                path = expr[9:]
                result[param_name] = MappingResolver.get_nested_value(payload, path)
            elif expr.startswith("@const:"):
                result[param_name] = expr[7:]
            else:
                result[param_name] = expr

        return result


__all__ = ["OutputActionExecutor"]
