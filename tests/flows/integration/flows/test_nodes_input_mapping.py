"""
Интеграционные тесты для нод с input_mapping.

БЕЗ МОКОВ (кроме LLM согласно правилам проекта).
Тестирует реальную работу маппинга в нодах.
"""

import pytest

from apps.flows.src.runtime.nodes import (
    LlmNode,
    FlowNode,
    RemoteFlowNode,
    ExternalAPINode,
    CodeNode,
    CodeNode,
)
from apps.flows.src.models.external_api import ParameterSchema
from core.state import ExecutionState


class TestBaseNodeInputMapping:
    """Тесты для BaseNode._resolve_inputs и _prepare_state."""

    def test_no_mapping_returns_empty_dict(self):
        """Без input_mapping возвращается пустой dict"""
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": None
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Hello",
            messages=[],
            variables={"x": 1}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs == {}

    def test_simple_state_mapping(self):
        """Простой маппинг @state:field"""
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "content": "@state:user_query",
                    "name": "@state:user_name"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_query="Привет!",
            user_name="Иван",
            other_field="should_not_be_in_inputs",
            variables={"company": "ACME"}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["content"] == "Привет!"
        assert inputs["name"] == "Иван"
        assert "other_field" not in inputs
        assert "user_query" not in inputs

    def test_nested_state_mapping(self):
        """Маппинг с вложенными путями @state:user.profile.name"""
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "user_name": "@state:user.profile.name",
                    "user_city": "@state:user.address.city"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user={
                "profile": {"name": "Иван", "age": 30},
                "address": {"city": "Москва", "street": "Ленина"}
            },
            variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["user_name"] == "Иван"
        assert inputs["user_city"] == "Москва"

    def test_var_mapping(self):
        """Маппинг с @var: для переменных"""
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "content": "@state:query",
                    "company": "@var:company_name",
                    "api_key": "@var:config.api_key"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            query="Hello!",
            variables={
                "company_name": "ACME Corp",
                "config": {"api_key": "secret123"}
            }
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["content"] == "Hello!"
        assert inputs["company"] == "ACME Corp"
        assert inputs["api_key"] == "secret123"

    def test_constant_values(self):
        """Маппинг с константами"""
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "content": "@state:query",
                    "fixed_value": "constant",
                    "number": 42,
                    "flag": True
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            query="Hello!",
            variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["content"] == "Hello!"
        assert inputs["fixed_value"] == "constant"
        assert inputs["number"] == 42
        assert inputs["flag"] is True

    def test_missing_path_returns_none(self):
        """Отсутствующий путь -> None"""
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {
                    "existing": "@state:existing",
                    "missing": "@state:missing.path"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            existing="value",
            variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["existing"] == "value"
        assert inputs["missing"] is None


class TestPrepareState:
    """Тесты для BaseNode._prepare_state."""

    def test_prepare_state_applies_inputs(self):
        """_prepare_state применяет inputs к state"""
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Test prompt",
                "input_mapping": {"content": "@state:query"}
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="123",
            query="Hello!",
            variables={"x": 1},
            session_id="test-agent:test-context",
            mock={"enabled": True}
        )
        
        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)
        
        assert result.content == "Hello!"
        assert result.variables == {"x": 1}
        assert result.user_id == "123"
        assert result.session_id == "test-agent:test-context"
        assert result.mock == {"enabled": True}


class TestAgentNodeInputMapping:
    """Тесты для FlowNode с input_mapping."""

    def test_no_mapping_returns_empty_inputs(self):
        """Без input_mapping inputs пустой"""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "inner_flow",
                "input_mapping": None
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Hello",
            variables={"x": 1}
        )
        
        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)
        
        assert result.model_dump() == state.model_dump()
        assert result is not state

    def test_simple_mapping(self):
        """Простой маппинг"""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "inner_flow",
                "input_mapping": {
                    "content": "@state:user_query",
                    "context": "@state:ctx"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_query="Привет!",
            ctx={"key": "value"},
            other="not_mapped",
            variables={"company": "ACME"}
        )
        
        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)
        
        assert result.content == "Привет!"
        assert result.context == {"key": "value"}
        assert result.variables == {"company": "ACME"}

    def test_nested_paths(self):
        """Вложенные пути"""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "inner_flow",
                "input_mapping": {
                    "name": "@state:user.profile.name",
                    "city": "@state:delivery.address.city"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user={"profile": {"name": "Иван"}},
            delivery={"address": {"city": "Москва"}},
            variables={}
        )
        
        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)
        
        assert result.name == "Иван"
        assert result.city == "Москва"

    def test_var_mapping(self):
        """Маппинг с @var:"""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "inner_flow",
                "input_mapping": {
                    "content": "@state:query",
                    "api_url": "@var:config.api_url"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            query="Hello!",
            variables={
                "config": {"api_url": "https://api.example.com"}
            }
        )
        
        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)
        
        assert result.content == "Hello!"
        assert result.api_url == "https://api.example.com"


class TestRemoteFlowNodeInputMapping:
    """Тесты для RemoteFlowNode с input_mapping."""

    def test_input_mapping_simple(self):
        """input_mapping: {"content": "@state:field"}"""
        node = RemoteFlowNode(
            node_id="test_remote",
            config={
                "url": "http://agent:8080",
                "input_mapping": {"content": "@state:user_query"}
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_query="Привет, агент!",
            variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["content"] == "Привет, агент!"

    def test_input_mapping_nested_path(self):
        """input_mapping с вложенным путём"""
        node = RemoteFlowNode(
            node_id="test_remote",
            config={
                "url": "http://agent:8080",
                "input_mapping": {"content": "@state:request.body.text"}
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            request={"body": {"text": "Nested query"}},
            variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["content"] == "Nested query"

    def test_input_mapping_with_var(self):
        """input_mapping с @var:"""
        node = RemoteFlowNode(
            node_id="test_remote",
            config={
                "url": "http://agent:8080",
                "input_mapping": {"content": "@var:default_prompt"}
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"default_prompt": "Default message"}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["content"] == "Default message"

    def test_no_mapping_uses_state_content(self):
        """Без input_mapping используется state.content"""
        node = RemoteFlowNode(
            node_id="test_remote",
            config={"url": "http://agent:8080"}
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Default content",
            variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs == {}


class TestExternalAPINodeParameterSource:
    """Тесты для ExternalAPINode с source в параметрах."""

    def test_parameter_with_state_source(self):
        """Параметр с source: @state:path"""
        # Создаём параметры с source
        param = ParameterSchema(
            name="city",
            source="@state:user.address.city",
            location="query"
        )
        
        assert param.name == "city"
        assert param.source == "@state:user.address.city"
        assert param.location.value == "query"

    def test_parameter_with_var_source(self):
        """Параметр с source: @var:name"""
        param = ParameterSchema(
            name="api_key",
            source="@var:weather.api_key",
            location="header"
        )
        
        assert param.name == "api_key"
        assert param.source == "@var:weather.api_key"

    def test_parameter_without_source(self):
        """Параметр без source (обратная совместимость)"""
        param = ParameterSchema(
            name="query",
            location="query",
            type="string",
            required=True
        )
        
        assert param.name == "query"
        assert param.source is None

    def test_parameter_with_default(self):
        """Параметр с default"""
        param = ParameterSchema(
            name="limit",
            type="integer",
            default=10
        )
        
        assert param.name == "limit"
        assert param.default == 10


class TestExternalAPINodeResolveArgs:
    """Тесты для резолвинга аргументов в ExternalAPINode.

    Тестируем логику выбора источника значения:
    1. source (если указан) -> MappingResolver.resolve_value
    2. state[param.name] (обратная совместимость)
    3. param.default (если есть)
    """

    def test_source_has_priority(self):
        """source имеет приоритет над state[param.name]"""
        from apps.flows.src.mapping import MappingResolver
        
        param = ParameterSchema(
            name="city",
            source="@state:user.city"
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            city="from_direct_state",  # Игнорируется
            user={"city": "from_source_path"},  # Используется
            variables={}
        )
        
        # source указан -> используем MappingResolver
        result = MappingResolver.resolve_value(param.source, state.model_dump())
        
        assert result == "from_source_path"

    def test_var_source_works(self):
        """@var: работает в source"""
        from apps.flows.src.mapping import MappingResolver
        
        param = ParameterSchema(
            name="api_key",
            source="@var:config.api_key"
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            api_key="from_direct",  # Игнорируется
            variables={
                "config": {"api_key": "from_var"}
            }
        )
        
        result = MappingResolver.resolve_value(param.source, state.model_dump())
        
        assert result == "from_var"

    def test_fallback_to_state_name(self):
        """Без source берётся state[param.name]"""
        param = ParameterSchema(
            name="city"
            # source не указан
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            city="Moscow",
            variables={}
        )
        
        # source None -> берём напрямую из state
        assert param.source is None
        assert state.get(param.name) == "Moscow"

    def test_fallback_to_default(self):
        """Без source и state[name] используется default"""
        param = ParameterSchema(
            name="limit",
            default=10
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={}
        )
        
        assert param.source is None
        assert param.name not in state
        assert param.default == 10


class TestAuthHeadersWithNestedVars:
    """Тесты для auth_headers с вложенными @var: путями."""

    def test_remote_flow_resolve_value_simple(self):
        """RemoteFlowNode._resolve_value с простым @var:"""
        node = RemoteFlowNode(
            node_id="test",
            config={"url": "http://agent:8080"}
        )
        variables = {"token": "abc123"}
        
        result = node._resolve_value("Bearer @var:token", variables)
        
        assert result == "Bearer abc123"

    def test_remote_flow_resolve_value_nested(self):
        """RemoteFlowNode._resolve_value с вложенным @var:"""
        node = RemoteFlowNode(
            node_id="test",
            config={"url": "http://agent:8080"}
        )
        variables = {
            "auth": {
                "bearer": "eyJhbGciOiJIUzI1NiJ9.test"
            }
        }
        
        result = node._resolve_value("Bearer @var:auth.bearer", variables)
        
        assert result == "Bearer eyJhbGciOiJIUzI1NiJ9.test"

    def test_remote_flow_resolve_auth_headers(self):
        """RemoteFlowNode._resolve_auth_headers с вложенными @var:"""
        node = RemoteFlowNode(
            node_id="test",
            config={
                "url": "http://agent:8080",
                "auth_headers": {
                    "Authorization": "Bearer @var:auth.token",
                    "X-API-Key": "@var:api.keys.primary"
                }
            }
        )
        variables = {
            "auth": {"token": "jwt_token_123"},
            "api": {"keys": {"primary": "pk_live_abc"}}
        }
        
        result = node._resolve_auth_headers(node.auth_headers_config, variables)
        
        assert result["Authorization"] == "Bearer jwt_token_123"
        assert result["X-API-Key"] == "pk_live_abc"

    def test_remote_flow_url_with_nested_var(self):
        """RemoteFlowNode URL с вложенным @var:"""
        node = RemoteFlowNode(
            node_id="test",
            config={"url": "https://@var:config.api.host/v1"}
        )
        variables = {
            "config": {
                "api": {"host": "api.example.com"}
            }
        }
        
        result = node._resolve_value(node.url, variables)
        
        assert result == "https://api.example.com/v1"


class TestExternalAPIClientAuthHeaders:
    """Тесты для ExternalAPIClient с auth_headers."""

    def test_resolve_value_simple_var(self):
        """ExternalAPIClient._resolve_value с простым @var:"""
        from apps.flows.src.clients.external_api_client import ExternalAPIClient
        
        client = ExternalAPIClient()
        variables = {"api_key": "secret123"}
        
        result = client._resolve_value("@var:api_key", variables)
        
        assert result == "secret123"

    def test_resolve_value_nested_var(self):
        """ExternalAPIClient._resolve_value с вложенным @var:"""
        from apps.flows.src.clients.external_api_client import ExternalAPIClient
        
        client = ExternalAPIClient()
        variables = {
            "config": {
                "credentials": {
                    "api_key": "nested_secret"
                }
            }
        }
        
        result = client._resolve_value("@var:config.credentials.api_key", variables)
        
        assert result == "nested_secret"

    def test_resolve_value_bearer_token_nested(self):
        """Bearer token с вложенным путём"""
        from apps.flows.src.clients.external_api_client import ExternalAPIClient
        
        client = ExternalAPIClient()
        variables = {
            "auth": {
                "tokens": {
                    "access": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
                }
            }
        }
        
        result = client._resolve_value("Bearer @var:auth.tokens.access", variables)
        
        assert result == "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"

    def test_build_headers_with_nested_vars(self):
        """ExternalAPIClient._build_headers с вложенными @var:"""
        from apps.flows.src.clients.external_api_client import ExternalAPIClient
        from apps.flows.src.models.external_api import ExternalAPIConfig, HTTPMethod
        
        client = ExternalAPIClient()
        config = ExternalAPIConfig(
            api_id="test_api",
            name="test_api",
            url="https://api.example.com",
            method=HTTPMethod.GET,
            headers={"Content-Type": "application/json"},
            auth_headers={
                "Authorization": "Bearer @var:auth.access_token",
                "X-API-Key": "@var:credentials.api.key"
            }
        )
        variables = {
            "auth": {"access_token": "jwt_123"},
            "credentials": {"api": {"key": "api_key_456"}}
        }
        
        headers = client._build_headers(config, variables)
        
        assert headers["Authorization"] == "Bearer jwt_123"
        assert headers["X-API-Key"] == "api_key_456"
        assert headers["Content-Type"] == "application/json"

    def test_resolve_url_with_nested_vars(self):
        """ExternalAPIClient._resolve_url с вложенными @var:"""
        from apps.flows.src.clients.external_api_client import ExternalAPIClient
        
        client = ExternalAPIClient()
        variables = {
            "api": {
                "host": "api.weather.com",
                "version": "v3"
            }
        }
        args = {}
        
        result = client._resolve_url(
            "https://@var:api.host/@var:api.version/forecast",
            args,
            variables
        )
        
        assert result == "https://api.weather.com/v3/forecast"

    def test_resolve_url_with_nested_vars_and_path_params(self):
        """URL с вложенными @var: и path параметрами"""
        from apps.flows.src.clients.external_api_client import ExternalAPIClient
        
        client = ExternalAPIClient()
        variables = {
            "config": {"base_url": "https://api.example.com"}
        }
        args = {"user_id": "123"}
        
        result = client._resolve_url(
            "@var:config.base_url/users/{user_id}",
            args,
            variables
        )
        
        assert result == "https://api.example.com/users/123"


class TestRealWorldScenarios:
    """Реальные сценарии использования input_mapping."""

    def test_order_processing_agent(self):
        """Агент обработки заказов с вложенными данными"""
        node = LlmNode(
            node_id="order_agent",
            config={
                "prompt": "Process order",
                "input_mapping": {
                    "order_id": "@state:order.id",
                    "customer_name": "@state:order.customer.name",
                    "items": "@state:order.items",
                    "total": "@state:order.total",
                    "company": "@var:company_name"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            order={
                "id": "ORD-12345",
                "customer": {"name": "Иван Петров", "email": "ivan@example.com"},
                "items": [{"name": "Item 1", "qty": 2}],
                "total": 999.99
            },
            variables={"company_name": "ACME Corp"}
        )
        
        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)
        
        assert result.order_id == "ORD-12345"
        assert result.customer_name == "Иван Петров"
        assert result.items == [{"name": "Item 1", "qty": 2}]
        assert result.total == 999.99
        assert result.company == "ACME Corp"

    def test_api_call_with_auth(self):
        """API вызов с авторизацией из переменных"""
        from apps.flows.src.mapping import MappingResolver
        
        auth_mapping = {
            "Authorization": "@var:auth.bearer_token",
            "X-API-Key": "@var:auth.api_key"
        }
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={
                "auth": {
                    "bearer_token": "Bearer eyJ...",
                    "api_key": "pk_live_abc123"
                }
            }
        )
        
        headers = MappingResolver.build_mapped_state(
            auth_mapping, state.model_dump()
        )
        
        assert headers["Authorization"] == "Bearer eyJ..."
        assert headers["X-API-Key"] == "pk_live_abc123"

    def test_subflow_with_filtered_data(self):
        """Subflow получает только нужные данные"""
        node = FlowNode(
            node_id="analysis_subflow",
            config={
                "flow_id": "document_analysis",
                "input_mapping": {
                    "content": "@state:document.text",
                    "metadata": "@state:document.meta",
                    "analysis_type": "@var:settings.analysis_type"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            document={
                "id": "doc-123",
                "text": "Document content here",
                "meta": {"author": "John", "date": "2024-01-01"},
                "binary_data": b"huge binary content"
            },
            other_data="not needed",
            variables={
                "settings": {"analysis_type": "sentiment"}
            }
        )
        
        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)
        
        assert result.content == "Document content here"
        assert result.metadata == {"author": "John", "date": "2024-01-01"}
        assert result.analysis_type == "sentiment"

    def test_remote_flow_context_injection(self):
        """Remote agent получает контекст из переменных"""
        node = RemoteFlowNode(
            node_id="external_agent",
            config={
                "url": "http://agent:8080",
                "input_mapping": {
                    "content": "@state:user_message",
                    "system_context": "@var:agent.system_prompt",
                    "user_info": "@state:session.user"
                }
            }
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_message="Какая погода в Москве?",
            session={
                "user": {"name": "Иван", "lang": "ru"}
            },
            variables={
                "agent": {
                    "system_prompt": "Ты помощник по погоде"
                }
            }
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["content"] == "Какая погода в Москве?"
        assert inputs["system_context"] == "Ты помощник по погоде"
        assert inputs["user_info"] == {"name": "Иван", "lang": "ru"}


class TestMessagesFilter:
    """Тесты для фильтрации messages."""

    def test_filter_all_returns_all_messages(self):
        """messages_filter='all' возвращает все сообщения"""
        from a2a.types import Message, Role, Part, TextPart
        
        node = LlmNode(
            node_id="test_node",
            config={
                "prompt": "Test",
                "messages_filter": "all"
            }
        )
        messages = [
            Message(
                messageId="1", role=Role.user,
                parts=[Part(root=TextPart(text="User msg"))],
                taskId="test", metadata={"node_id": "other_node"}
            ),
            Message(
                messageId="2", role=Role.agent,
                parts=[Part(root=TextPart(text="Agent msg"))],
                taskId="test", metadata={"node_id": "test_node"}
            ),
            Message(
                messageId="3", role=Role.agent,
                parts=[Part(root=TextPart(text="Another agent"))],
                taskId="test", metadata={"node_id": "another_node"}
            ),
        ]
        state = ExecutionState(
            task_id="test", context_id="ctx", user_id="u",
            session_id="test:ctx", messages=messages, variables={}
        )
        
        result = node._get_filtered_messages(state)
        
        assert len(result) == 3

    def test_filter_own_returns_own_and_user_messages(self):
        """messages_filter='own' возвращает свои + user сообщения"""
        from a2a.types import Message, Role, Part, TextPart
        
        node = LlmNode(
            node_id="test_node",
            config={
                "prompt": "Test",
                "messages_filter": "own"
            }
        )
        messages = [
            Message(
                messageId="1", role=Role.user,
                parts=[Part(root=TextPart(text="User msg"))],
                taskId="test", metadata={}
            ),
            Message(
                messageId="2", role=Role.agent,
                parts=[Part(root=TextPart(text="My msg"))],
                taskId="test", metadata={"node_id": "test_node"}
            ),
            Message(
                messageId="3", role=Role.agent,
                parts=[Part(root=TextPart(text="Other msg"))],
                taskId="test", metadata={"node_id": "other_node"}
            ),
        ]
        state = ExecutionState(
            task_id="test", context_id="ctx", user_id="u",
            session_id="test:ctx", messages=messages, variables={}
        )
        
        result = node._get_filtered_messages(state)
        
        assert len(result) == 2
        assert result[0].message_id == "1"
        assert result[1].message_id == "2"

    def test_filter_list_returns_specified_nodes(self):
        """messages_filter=['node1', 'node2'] возвращает от указанных + user"""
        from a2a.types import Message, Role, Part, TextPart
        
        node = LlmNode(
            node_id="test_node",
            config={
                "prompt": "Test",
                "messages_filter": ["node1", "node2"]
            }
        )
        messages = [
            Message(
                messageId="1", role=Role.user,
                parts=[Part(root=TextPart(text="User"))],
                taskId="test", metadata={}
            ),
            Message(
                messageId="2", role=Role.agent,
                parts=[Part(root=TextPart(text="From node1"))],
                taskId="test", metadata={"node_id": "node1"}
            ),
            Message(
                messageId="3", role=Role.agent,
                parts=[Part(root=TextPart(text="From node3"))],
                taskId="test", metadata={"node_id": "node3"}
            ),
            Message(
                messageId="4", role=Role.agent,
                parts=[Part(root=TextPart(text="From node2"))],
                taskId="test", metadata={"node_id": "node2"}
            ),
        ]
        state = ExecutionState(
            task_id="test", context_id="ctx", user_id="u",
            session_id="test:ctx", messages=messages, variables={}
        )
        
        result = node._get_filtered_messages(state)
        
        assert len(result) == 3
        ids = [m.message_id for m in result]
        assert "1" in ids
        assert "2" in ids
        assert "4" in ids
        assert "3" not in ids


class TestSaveToMessages:
    """Тесты для save_to_messages."""

    def test_append_to_messages_adds_message_with_node_id(self):
        """_append_to_messages добавляет сообщение с node_id в metadata"""
        node = LlmNode(
            node_id="my_node",
            config={
                "prompt": "Test",
                "save_to_messages": True
            }
        )
        state = ExecutionState(
            task_id="test-task", context_id="ctx", user_id="u",
            session_id="test:ctx", messages=[], variables={}
        )
        
        node._append_to_messages(state, "Result text")
        
        assert len(state.messages) == 1
        msg = state.messages[0]
        assert msg.metadata["node_id"] == "my_node"
        assert msg.parts[0].root.text == "Result text"

    def test_output_mapping_from_config(self):
        """output_mapping можно задать в config"""
        node = LlmNode(
            node_id="my_agent",
            config={
                "prompt": "Test",
                "output_mapping": {"response": "agent_response"}
            }
        )
        
        assert node.output_mapping == {"response": "agent_response"}


class TestCodeNodeInputMapping:
    """Тесты для CodeNode с input_mapping."""

    def test_tool_node_resolves_inputs(self):
        """CodeNode использует input_mapping для аргументов"""
        from apps.flows.src.tools.base import BaseTool
        
        class MockTool(BaseTool):
            name = "mock_tool"
            description = "Test tool"
            
            async def _run_impl(self, args, state):
                return f"Got: {args.get('query')}"
        
        node = CodeNode(
            node_id="test_tool",
            config={"input_mapping": {"query": "@state:user_input"}}
        )
        node.tool = MockTool()
        state = ExecutionState(
            task_id="test", context_id="ctx", user_id="u",
            session_id="test:ctx", user_input="Hello", variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["query"] == "Hello"


class TestCodeNodeInputMapping:
    """Тесты для CodeNode с input_mapping."""

    def test_function_node_resolves_inputs(self):
        """CodeNode использует input_mapping для kwargs"""
        # Lambda не поддерживается напрямую в config, используем callable в code
        def test_func(state, name=""):
            return state
        
        node = CodeNode(
            node_id="test_func",
            config={
                "code": test_func,
                "input_mapping": {"name": "@state:user_name"}
            }
        )
        state = ExecutionState(
            task_id="test", context_id="ctx", user_id="u",
            session_id="test:ctx", user_name="Иван", variables={}
        )
        
        inputs = node._resolve_inputs(state)
        
        assert inputs["name"] == "Иван"

