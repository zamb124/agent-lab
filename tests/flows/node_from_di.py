from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.nodes import BaseNode
from core.types import JsonObject


class NodeFromDi(BaseNode):
    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        di,
    ) -> None:
        super().__init__(
            node_id,
            config,
            execution=execution_context_for(di.workflow_runtime),
            redis_client=di.redis_client,
        )
