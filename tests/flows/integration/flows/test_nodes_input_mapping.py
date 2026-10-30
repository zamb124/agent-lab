"""
Интеграционные тесты для нод с input_mapping.

БЕЗ МОКОВ (кроме LLM согласно правилам проекта).
Тестирует реальную работу маппинга в нодах.
"""

from a2a.types import Message, Part
from a2a.types.a2a_pb2 import ROLE_AGENT, ROLE_USER

from apps.flows.di import FlowsDi
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.nodes import (
    CodeNode,
    FlowNode,
    LlmNode,
    RemoteFlowNode,
)
from apps.flows.src.state import ExecutionState
from core.types import JsonObject
from core.variables import VariableResolver


def _typed_config(node_type: NodeType, config: JsonObject) -> JsonObject:
    if "type" in config:
        raise ValueError("test node config must not override canonical node type")
    return {"type": node_type.value, **config}


def llm_node(di: FlowsDi, *, node_id: str, config: JsonObject) -> LlmNode:
    return LlmNode(
        node_id=node_id,
        config=_typed_config(NodeType.LLM_NODE, config),
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, llm_context_memory_store=di.node_constructor.llm_context_memory_store, namespace_service=di.node_constructor.namespace_service, authz_service=di.node_constructor.authz_service, tool_registry=di.tool_registry, workflow_runtime=di.node_constructor.workflow_runtime, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory,
    )


def flow_node(di: FlowsDi, *, node_id: str, config: JsonObject) -> FlowNode:
    return FlowNode(
        node_id=node_id,
        config=_typed_config(NodeType.FLOW, config),
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, tool_registry=di.tool_registry, handoff_orchestrator_service=di.handoff_orchestrator_service,
    )


def remote_flow_node(
    di: FlowsDi,
    *,
    node_id: str,
    config: JsonObject,
) -> RemoteFlowNode:
    return RemoteFlowNode(
        node_id=node_id,
        config=_typed_config(NodeType.REMOTE_FLOW, config),
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, a2a_client=di.node_constructor.a2a_client, emitter_factory=di.node_constructor.emitter_factory,
    )


def code_node(di: FlowsDi, *, node_id: str, config: JsonObject) -> CodeNode:
    return CodeNode(
        node_id=node_id,
        config=_typed_config(NodeType.CODE, config),
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client,
    )


class TestBaseNodeInputMapping:
    """Тесты для BaseNode._resolve_inputs и _prepare_state."""

    def test_no_mapping_returns_empty_dict(self, di: FlowsDi, unique_id):
        """Без input_mapping возвращается пустой dict"""
        node = llm_node(
            di, node_id="test_agent", config={"prompt": "Test prompt", "input_mapping": None}
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            content="Hello",
            messages=[],
            variables={"x": 1},
        )

        inputs = node._resolve_inputs(state)

        assert inputs == {}

    def test_simple_state_mapping(self, di: FlowsDi, unique_id):
        """Простой маппинг @state:field"""
        node = llm_node(
            di,
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {"content": "@state:user_query", "name": "@state:user_name"},
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            user_query="Привет!",
            user_name="Иван",
            other_field="should_not_be_in_inputs",
            variables={"company": "ACME"},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "Привет!"
        assert inputs["name"] == "Иван"
        assert "other_field" not in inputs
        assert "user_query" not in inputs

    def test_llm_mapped_inputs_are_prompt_variables_with_explicit_precedence(
        self, di: FlowsDi,
        unique_id,
    ):
        node = llm_node(
            di,
            node_id="test_agent",
            config={
                "prompt": "Topic={topic}; company={company}",
                "input_mapping": {"topic": "@state:upstream_topic"},
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            upstream_topic="mapped topic",
            variables={"topic": "old topic", "company": "ACME"},
        )

        inputs = node._resolve_inputs(state)
        prepared = node._prepare_llm_runner_state(state, inputs)
        rendered = VariableResolver.render_template(node.prompt_template, prepared.variables)

        assert prepared.variables == {"topic": "mapped topic", "company": "ACME"}
        assert rendered == "Topic=mapped topic; company=ACME"

    def test_nested_state_mapping(self, di: FlowsDi, unique_id):
        """Маппинг с вложенными путями @state:user.profile.name"""
        node = llm_node(
            di,
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "user_name": "@state:user.profile.name",
                    "user_city": "@state:user.address.city",
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            user={
                "profile": {"name": "Иван", "age": 30},
                "address": {"city": "Москва", "street": "Ленина"},
            },
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["user_name"] == "Иван"
        assert inputs["user_city"] == "Москва"

    def test_var_mapping(self, di: FlowsDi, unique_id):
        """Маппинг с @var: для переменных"""
        node = llm_node(
            di,
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "content": "@state:query",
                    "company": "@var:company_name",
                    "api_key": "@var:config.api_key",
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            query="Hello!",
            variables={"company_name": "ACME Corp", "config": {"api_key": "secret123"}},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "Hello!"
        assert inputs["company"] == "ACME Corp"
        assert inputs["api_key"] == "secret123"

    def test_constant_values(self, di: FlowsDi, unique_id):
        """Маппинг с константами"""
        node = llm_node(
            di,
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "content": "@state:query",
                    "fixed_value": "constant",
                    "number": 42,
                    "flag": True,
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            query="Hello!",
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "Hello!"
        assert inputs["fixed_value"] == "constant"
        assert inputs["number"] == 42
        assert inputs["flag"] is True

    def test_missing_path_returns_none(self, di: FlowsDi, unique_id):
        """Отсутствующий путь -> None"""
        node = llm_node(
            di,
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {"existing": "@state:existing", "missing": "@state:missing.path"},
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            existing="value",
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["existing"] == "value"
        assert inputs["missing"] is None


class TestPrepareState:
    """Тесты для BaseNode._prepare_state."""

    def test_prepare_state_applies_inputs(self, di: FlowsDi, unique_id):
        """_prepare_state применяет inputs к state"""
        node = llm_node(
            di,
            node_id="test_agent",
            config={"prompt": "Test prompt", "input_mapping": {"content": "@state:query"}},
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="123",
            query="Hello!",
            variables={"x": 1},
            session_id=f"test-agent:test-context-{unique_id}",
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "Hello!"
        assert result.variables == {"x": 1}
        assert result.user_id == "123"
        assert result.session_id == f"test-agent:test-context-{unique_id}"


class TestAgentNodeInputMapping:
    """Тесты для FlowNode с input_mapping."""

    def test_no_mapping_returns_empty_inputs(self, di: FlowsDi, unique_id):
        """Без input_mapping inputs пустой"""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={"flow_id": "inner_flow", "input_mapping": None},
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            content="Hello",
            variables={"x": 1},
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.model_dump() == state.model_dump()
        assert result is not state

    def test_simple_mapping(self, di: FlowsDi, unique_id):
        """Простой маппинг"""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={
                "flow_id": "inner_flow",
                "input_mapping": {"content": "@state:user_query", "context": "@state:ctx"},
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            user_query="Привет!",
            ctx={"key": "value"},
            other="not_mapped",
            variables={"company": "ACME"},
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "Привет!"
        assert result.context == {"key": "value"}
        assert result.variables == {"company": "ACME"}

    def test_nested_paths(self, di: FlowsDi, unique_id):
        """Вложенные пути"""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={
                "flow_id": "inner_flow",
                "input_mapping": {
                    "name": "@state:user.profile.name",
                    "city": "@state:delivery.address.city",
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            user={"profile": {"name": "Иван"}},
            delivery={"address": {"city": "Москва"}},
            variables={},
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.name == "Иван"
        assert result.city == "Москва"

    def test_var_mapping(self, di: FlowsDi, unique_id):
        """Маппинг с @var:"""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={
                "flow_id": "inner_flow",
                "input_mapping": {"content": "@state:query", "api_url": "@var:config.api_url"},
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            query="Hello!",
            variables={"config": {"api_url": "https://api.example.com"}},
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "Hello!"
        assert result.api_url == "https://api.example.com"


class TestRemoteFlowNodeInputMapping:
    """Тесты для RemoteFlowNode с input_mapping."""

    def test_input_mapping_simple(self, di: FlowsDi, unique_id):
        """input_mapping: {"content": "@state:field"}"""
        node = remote_flow_node(
            di,
            node_id="test_remote",
            config={"url": "http://agent:8080", "input_mapping": {"content": "@state:user_query"}},
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            user_query="Привет, агент!",
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "Привет, агент!"

    def test_input_mapping_nested_path(self, di: FlowsDi, unique_id):
        """input_mapping с вложенным путём"""
        node = remote_flow_node(
            di,
            node_id="test_remote",
            config={
                "url": "http://agent:8080",
                "input_mapping": {"content": "@state:request.body.text"},
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            request={"body": {"text": "Nested query"}},
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "Nested query"

    def test_input_mapping_with_var(self, di: FlowsDi, unique_id):
        """input_mapping с @var:"""
        node = remote_flow_node(
            di,
            node_id="test_remote",
            config={
                "url": "http://agent:8080",
                "input_mapping": {"content": "@var:default_prompt"},
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            variables={"default_prompt": "Default message"},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "Default message"

    def test_no_mapping_uses_state_content(self, di: FlowsDi, unique_id):
        """Без input_mapping используется state.content"""
        node = remote_flow_node(
            di, node_id="test_remote", config={"url": "http://agent:8080"}
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            content="Default content",
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs == {}


class TestHeadersWithNestedVars:
    """Тесты для headers/URL с вложенными @var: путями."""

    def test_remote_flow_resolve_value_simple(self, unique_id):
        """Простой @var: в строке заголовка через MappingResolver."""
        from apps.flows.src.mapping import MappingResolver

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            variables={"token": "abc123"},
        )

        result = MappingResolver.resolve_http_header_value(
            "Bearer @var:token",
            state,
            state.variables,
        )

        assert result == "Bearer abc123"

    def test_remote_flow_resolve_value_nested(self, unique_id):
        """Строковый заголовок/URL с вложенным @var: через MappingResolver."""
        from apps.flows.src.mapping import MappingResolver

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            variables={"auth": {"bearer": "eyJhbGciOiJIUzI1NiJ9.test"}},
        )

        result = MappingResolver.resolve_http_header_value(
            "Bearer @var:auth.bearer",
            state,
            state.variables,
        )

        assert result == "Bearer eyJhbGciOiJIUzI1NiJ9.test"

    def test_remote_flow_resolve_headers_dict(self, di: FlowsDi, unique_id):
        """RemoteFlowNode._resolve_headers_dict с вложенными @var:"""
        node = remote_flow_node(
            di,
            node_id="test",
            config={
                "url": "http://agent:8080",
                "headers": {
                    "Authorization": "Bearer @var:auth.token",
                    "X-API-Key": "@var:api.keys.primary",
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            variables={
                "auth": {"token": "jwt_token_123"},
                "api": {"keys": {"primary": "pk_live_abc"}},
            },
        )

        result = node._resolve_headers_dict(node.headers_config, state, state.variables)

        assert result["Authorization"] == "Bearer jwt_token_123"
        assert result["X-API-Key"] == "pk_live_abc"

    def test_remote_flow_url_with_nested_var(self, unique_id):
        """URL с вложенным @var:"""
        from apps.flows.src.mapping import MappingResolver

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            variables={"config": {"api": {"host": "api.example.com"}}},
        )

        result = MappingResolver.resolve_http_header_value(
            "https://@var:config.api.host/v1",
            state,
            state.variables,
        )

        assert result == "https://api.example.com/v1"


class TestExternalAPIClientHeaders:
    """Тесты для ExternalAPIClient и MappingResolver (@var:@state: в url/headers)."""

    def _state(self, variables, unique_id: str = "headers"):
        return ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            variables=variables,
        )

    def test_resolve_string_template_simple_var(self):
        """Строковый шаблон: простой @var:"""
        from apps.flows.src.mapping import MappingResolver

        variables = {"api_key": "secret123"}
        state = self._state(variables)

        assert (
            MappingResolver.resolve_http_header_value("@var:api_key", state, variables)
            == "secret123"
        )

    def test_resolve_string_template_nested_var(self):
        """Вложенный @var:"""
        from apps.flows.src.mapping import MappingResolver

        variables = {
            "config": {
                "credentials": {
                    "api_key": "nested_secret",
                },
            },
        }
        state = self._state(variables)

        assert (
            MappingResolver.resolve_http_header_value(
                "@var:config.credentials.api_key",
                state,
                variables,
            )
            == "nested_secret"
        )

    def test_resolve_string_template_bearer_nested(self):
        """Bearer token с токенами @var: в тексте."""
        from apps.flows.src.mapping import MappingResolver

        variables = {
            "auth": {
                "tokens": {
                    "access": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
                },
            },
        }
        state = self._state(variables)

        assert (
            MappingResolver.resolve_http_header_value(
                "Bearer @var:auth.tokens.access",
                state,
                variables,
            )
            == "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
        )
        """ExternalAPIClient._build_headers с вложенными @var:"""
        from apps.flows.src.models.external_api import ExternalAPIConfig, HTTPMethod
        from apps.flows.src.services.external_api_client import ExternalAPIClient

        client = ExternalAPIClient()
        config = ExternalAPIConfig(
            api_id="test_api",
            name="test_api",
            url="https://api.example.com",
            method=HTTPMethod.GET,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer @var:auth.access_token",
                "X-API-Key": "@var:credentials.api.key",
            },
        )
        variables = {
            "auth": {"access_token": "jwt_123"},
            "credentials": {"api": {"key": "api_key_456"}},
        }
        state = self._state(variables)

        headers = client._build_headers(config, state.variables, state)

        assert headers["Authorization"] == "Bearer jwt_123"
        assert headers["X-API-Key"] == "api_key_456"
        assert headers["Content-Type"] == "application/json"

    def test_resolve_url_with_nested_vars(self):
        """ExternalAPIClient._resolve_url с вложенными @var:"""
        from apps.flows.src.services.external_api_client import ExternalAPIClient

        client = ExternalAPIClient()
        variables = {
            "api": {
                "host": "api.weather.com",
                "version": "v3",
            },
        }
        args = {}
        state = self._state(variables)

        result = client._resolve_url(
            "https://@var:api.host/@var:api.version/forecast",
            args,
            variables,
            state,
        )

        assert result == "https://api.weather.com/v3/forecast"

    def test_resolve_url_with_nested_vars_and_path_params(self):
        """URL с вложенными @var: и path параметрами"""
        from apps.flows.src.services.external_api_client import ExternalAPIClient

        client = ExternalAPIClient()
        variables = {
            "config": {"base_url": "https://api.example.com"},
        }
        args = {"user_id": "123"}
        state = self._state(variables)

        result = client._resolve_url(
            "@var:config.base_url/users/{user_id}",
            args,
            variables,
            state,
        )

        assert result == "https://api.example.com/users/123"


class TestRealWorldScenarios:
    """Реальные сценарии использования input_mapping."""

    def test_order_processing_agent(self, di: FlowsDi, unique_id):
        """Агент обработки заказов с вложенными данными"""
        node = llm_node(
            di,
            node_id="order_agent",
            config={
                "prompt": "Process order",
                "input_mapping": {
                    "order_id": "@state:order.id",
                    "customer_name": "@state:order.customer.name",
                    "items": "@state:order.items",
                    "total": "@state:order.total",
                    "company": "@var:company_name",
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            order={
                "id": "ORD-12345",
                "customer": {"name": "Иван Петров", "email": "ivan@example.com"},
                "items": [{"name": "Item 1", "qty": 2}],
                "total": 999.99,
            },
            variables={"company_name": "ACME Corp"},
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.order_id == "ORD-12345"
        assert result.customer_name == "Иван Петров"
        assert result.items == [{"name": "Item 1", "qty": 2}]
        assert result.total == 999.99
        assert result.company == "ACME Corp"

    def test_api_call_with_auth(self, unique_id):
        """API вызов с авторизацией из переменных"""
        from apps.flows.src.mapping import MappingResolver

        auth_mapping = {"Authorization": "@var:auth.bearer_token", "X-API-Key": "@var:auth.api_key"}
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            variables={"auth": {"bearer_token": "Bearer eyJ...", "api_key": "pk_live_abc123"}},
        )

        headers = MappingResolver.build_mapped_state(auth_mapping, state.model_dump())

        assert headers["Authorization"] == "Bearer eyJ..."
        assert headers["X-API-Key"] == "pk_live_abc123"

    def test_subflow_with_filtered_data(self, di: FlowsDi, unique_id):
        """Subflow получает только нужные данные"""
        node = flow_node(
            di,
            node_id="analysis_subflow",
            config={
                "flow_id": "document_analysis",
                "input_mapping": {
                    "content": "@state:document.text",
                    "metadata": "@state:document.meta",
                    "analysis_type": "@var:settings.analysis_type",
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            document={
                "id": "doc-123",
                "text": "Document content here",
                "meta": {"author": "John", "date": "2024-01-01"},
                "binary_data": b"huge binary content",
            },
            other_data="not needed",
            variables={"settings": {"analysis_type": "sentiment"}},
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "Document content here"
        assert result.metadata == {"author": "John", "date": "2024-01-01"}
        assert result.analysis_type == "sentiment"

    def test_remote_flow_context_injection(self, di: FlowsDi, unique_id):
        """Remote agent получает контекст из переменных"""
        node = remote_flow_node(
            di,
            node_id="external_agent",
            config={
                "url": "http://agent:8080",
                "input_mapping": {
                    "content": "@state:user_message",
                    "system_context": "@var:agent.system_prompt",
                    "user_info": "@state:session.user",
                },
            },
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            user_message="Какая погода в Москве?",
            session={"user": {"name": "Иван", "lang": "ru"}},
            variables={"agent": {"system_prompt": "Ты помощник по погоде"}},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "Какая погода в Москве?"
        assert inputs["system_context"] == "Ты помощник по погоде"
        assert inputs["user_info"] == {"name": "Иван", "lang": "ru"}


class TestMessagesFilter:
    """Тесты для фильтрации messages."""

    def test_filter_all_returns_all_messages(self, di: FlowsDi):
        """messages_filter='all' возвращает все сообщения"""
        node = llm_node(
            di, node_id="test_node", config={"prompt": "Test", "messages_filter": "all"}
        )
        messages = [
            Message(
                message_id="1",
                role=ROLE_USER,
                parts=[Part(text="User msg")],
                task_id="test",
                metadata={"node_id": "other_node"},
            ),
            Message(
                message_id="2",
                role=ROLE_AGENT,
                parts=[Part(text="Agent msg")],
                task_id="test",
                metadata={"node_id": "test_node"},
            ),
            Message(
                message_id="3",
                role=ROLE_AGENT,
                parts=[Part(text="Another agent")],
                task_id="test",
                metadata={"node_id": "another_node"},
            ),
        ]
        state = ExecutionState(
            task_id="test",
            context_id="ctx",
            user_id="u",
            session_id="test:ctx",
            messages=messages,
            variables={},
        )

        result = node._get_filtered_messages(state)

        assert len(result) == 3

    def test_filter_own_returns_only_messages_tagged_with_node_id(
        self, di: FlowsDi
    ):
        """messages_filter='own' — только сообщения с metadata.node_id == эта нода"""
        node = llm_node(
            di, node_id="test_node", config={"prompt": "Test", "messages_filter": "own"}
        )
        messages = [
            Message(
                message_id="1",
                role=ROLE_USER,
                parts=[Part(text="User msg")],
                task_id="test",
                metadata={"node_id": "test_node"},
            ),
            Message(
                message_id="2",
                role=ROLE_AGENT,
                parts=[Part(text="My msg")],
                task_id="test",
                metadata={"node_id": "test_node"},
            ),
            Message(
                message_id="3",
                role=ROLE_AGENT,
                parts=[Part(text="Other msg")],
                task_id="test",
                metadata={"node_id": "other_node"},
            ),
            Message(
                message_id="4",
                role=ROLE_USER,
                parts=[Part(text="Other user")],
                task_id="test",
                metadata={"node_id": "other_node"},
            ),
        ]
        state = ExecutionState(
            task_id="test",
            context_id="ctx",
            user_id="u",
            session_id="test:ctx",
            messages=messages,
            variables={},
        )

        result = node._get_filtered_messages(state)

        assert len(result) == 2
        assert result[0].message_id == "1"
        assert result[1].message_id == "2"

    def test_filter_list_returns_specified_nodes(self, di: FlowsDi):
        """messages_filter=['node1', 'node2'] — только сообщения с node_id из списка"""
        node = llm_node(
            di,
            node_id="test_node",
            config={"prompt": "Test", "messages_filter": ["node1", "node2"]},
        )
        messages = [
            Message(
                message_id="1",
                role=ROLE_USER,
                parts=[Part(text="User")],
                task_id="test",
                metadata={"node_id": "node1"},
            ),
            Message(
                message_id="2",
                role=ROLE_AGENT,
                parts=[Part(text="From node1")],
                task_id="test",
                metadata={"node_id": "node1"},
            ),
            Message(
                message_id="3",
                role=ROLE_AGENT,
                parts=[Part(text="From node3")],
                task_id="test",
                metadata={"node_id": "node3"},
            ),
            Message(
                message_id="4",
                role=ROLE_AGENT,
                parts=[Part(text="From node2")],
                task_id="test",
                metadata={"node_id": "node2"},
            ),
            Message(
                message_id="5",
                role=ROLE_USER,
                parts=[Part(text="node3 user")],
                task_id="test",
                metadata={"node_id": "node3"},
            ),
        ]
        state = ExecutionState(
            task_id="test",
            context_id="ctx",
            user_id="u",
            session_id="test:ctx",
            messages=messages,
            variables={},
        )

        result = node._get_filtered_messages(state)

        assert len(result) == 3
        ids = [m.message_id for m in result]
        assert "1" in ids
        assert "2" in ids
        assert "4" in ids
        assert "3" not in ids
        assert "5" not in ids

    def test_own_filter_full_log_not_truncated(self, di: FlowsDi):
        """messages_filter=own сужает только срез для LLM; полный лог в state накапливается."""
        from apps.flows.src.runtime.runners.llm_runner import new_assistant_message

        node = llm_node(
            di,
            node_id="test_node",
            config={"prompt": "Test", "messages_filter": "own"},
        )
        messages = [
            Message(
                message_id="1",
                role=ROLE_USER,
                parts=[Part(text="u")],
                task_id="t",
                metadata={},
            ),
            Message(
                message_id="2",
                role=ROLE_AGENT,
                parts=[Part(text="other")],
                task_id="t",
                metadata={"node_id": "other"},
            ),
        ]
        state = ExecutionState(
            task_id="t",
            context_id="c",
            user_id="u",
            session_id="x:c",
            messages=messages,
            variables={},
        )
        full_before = len(state.messages)
        filtered = node._get_filtered_messages(state)
        assert len(filtered) < full_before
        state.messages.append(
            new_assistant_message("reply", "test_node", None, context_id="c", task_id="t")
        )
        assert len(state.messages) == full_before + 1

    def test_llm_runner_message_factories_tag_node_id(self):
        from apps.flows.src.runtime.runners.llm_runner import (
            new_assistant_message,
            new_tool_result_message,
            new_user_message,
        )

        u = new_user_message("hi", "n1", "ctx", "tid")
        assert u.metadata["node_id"] == "n1"
        a = new_assistant_message("a", "n1", [{"name": "t", "id": "1"}], "ctx", "tid")
        assert a.metadata["node_id"] == "n1"
        # metadata сообщения A2A — protobuf Struct: доступ по ключу и `in`,
        # без dict-метода get.
        assert "tool_calls" in a.metadata
        assert len(a.metadata["tool_calls"]) == 1
        tr = new_tool_result_message("1", "ok", "n1", "ctx", "tid")
        assert tr.metadata["node_id"] == "n1"


class TestSaveToMessages:
    """Тесты для save_to_messages."""

    def test_append_to_messages_adds_message_with_node_id(self, di: FlowsDi, unique_id):
        """_append_to_messages добавляет сообщение с node_id в metadata"""
        node = llm_node(
            di, node_id="my_node", config={"prompt": "Test", "save_to_messages": True}
        )
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id="ctx",
            user_id="u",
            session_id="test:ctx",
            messages=[],
            variables={},
        )

        node._append_to_messages(state, "Result text")

        assert len(state.messages) == 1
        msg = state.messages[0]
        assert msg.metadata["node_id"] == "my_node"
        assert msg.parts[0].text == "Result text"

    def test_output_mapping_from_config(self, di: FlowsDi):
        """output_mapping можно задать в config"""
        node = llm_node(
            di,
            node_id="my_agent",
            config={"prompt": "Test", "output_mapping": {"response": "agent_response"}},
        )

        assert node.output_mapping == {"response": "agent_response"}


class TestCodeNodeInputMapping:
    """Тесты для CodeNode с input_mapping."""

    def test_function_node_resolves_inputs(self, di: FlowsDi):
        """CodeNode использует input_mapping для kwargs"""

        node = code_node(
            di,
            node_id="test_func",
            config={
                "code": "async def run(args, state):\n    return {}",
                "input_mapping": {"name": "@state:user_name"},
            },
        )
        state = ExecutionState(
            task_id="test",
            context_id="ctx",
            user_id="u",
            session_id="test:ctx",
            user_name="Иван",
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["name"] == "Иван"
