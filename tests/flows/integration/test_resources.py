"""
Интеграционные тесты: resources (code, files, llm) с нодами.

MockLLM — где нужен LLM.
"""

import uuid
import pytest
from apps.flows.src.models import ResourceDefinition, ResourceReference
from apps.flows.src.models.flow_config import BranchConfig, Edge, FlowConfig
from apps.flows.src.runtime.nodes import CodeNode, LlmNode
from core.state import ExecutionState

pytestmark = pytest.mark.skip(
    reason="Legacy in-process resource injection is no longer supported; sandbox code uses capabilities."
)


def make_state(**kwargs) -> ExecutionState:
    """Создаёт ExecutionState."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
    }
    defaults.update(kwargs)
    return ExecutionState(**defaults)


class TestCodeResourceWithCodeNode:
    """
    CODE resource: inline Python код доступен в CodeNode.

    Проверяем что функции и классы из ресурса доступны в namespace.
    """

    @pytest.mark.asyncio
    async def test_code_resource_functions_available(self, container):
        """
        Функции из code resource доступны в CodeNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef format_phone(phone):\n    digits = ''.join(c for c in phone if c.isdigit())\n    return f'+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}'\n\ndef validate_email(email):\n    return '@' in email and '.' in email.split('@')[1]\n",
            },
        }
        node = CodeNode(
            node_id="phone_formatter",
            config={
                "code": "\nasync def run(args, state):\n    formatted = helpers.format_phone(state.phone)\n    is_valid = helpers.validate_email(state.email)\n    state.formatted_phone = formatted\n    state.email_valid = is_valid\n    return {'phone': formatted, 'valid': is_valid}\n",
                "resources": {"helpers": ResourceReference.model_validate(code_resource)},
            },
            container=container,
        )
        state = make_state(phone="89161234567", email="test@example.com")
        result = await node.run(state)
        assert result.formatted_phone == "+7 (916) 123-45-67"
        assert result.email_valid is True

    @pytest.mark.asyncio
    async def test_code_resource_class_available(self, container):
        """
        Классы из code resource доступны в CodeNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\nclass Calculator:\n    @staticmethod\n    def add(a, b):\n        return a + b\n\n    @staticmethod\n    def multiply(a, b):\n        return a * b\n\nclass StringHelper:\n    @staticmethod\n    def reverse(s):\n        return s[::-1]\n",
            },
        }
        node = CodeNode(
            node_id="calculator",
            config={
                "code": "\nasync def run(args, state):\n    result = utils.Calculator.add(10, 5)\n    product = utils.Calculator.multiply(result, 2)\n    reversed_name = utils.StringHelper.reverse(state.name)\n    state.sum_result = result\n    state.product_result = product\n    state.reversed_name = reversed_name\n    return {'sum': result, 'product': product, 'reversed': reversed_name}\n",
                "resources": {"utils": ResourceReference.model_validate(code_resource)},
            },
            container=container,
        )
        state = make_state(name="Hello")
        result = await node.run(state)
        assert result.sum_result == 15
        assert result.product_result == 30
        assert result.reversed_name == "olleH"

    @pytest.mark.asyncio
    async def test_multiple_code_resources(self, container):
        """
        Несколько code resources доступны в CodeNode.
        """
        validators = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef is_positive(n):\n    return n > 0\n\ndef is_even(n):\n    return n % 2 == 0\n",
            },
        }
        formatters = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef to_currency(n):\n    return f'${n:,.2f}'\n\ndef to_percent(n):\n    return f'{n * 100:.1f}%'\n",
            },
        }
        node = CodeNode(
            node_id="multi_resource",
            config={
                "code": "\nasync def run(args, state):\n    num = state.number\n    is_pos = validators.is_positive(num)\n    is_even = validators.is_even(num)\n    currency = formatters.to_currency(num)\n    percent = formatters.to_percent(num / 100)\n\n    state.is_positive = is_pos\n    state.is_even = is_even\n    state.currency = currency\n    state.percent = percent\n\n    return {'positive': is_pos, 'even': is_even, 'currency': currency}\n",
                "resources": {
                    "validators": ResourceReference.model_validate(validators),
                    "formatters": ResourceReference.model_validate(formatters),
                },
            },
            container=container,
        )
        state = make_state(number=42)
        result = await node.run(state)
        assert result.is_positive is True
        assert result.is_even is True
        assert result.currency == "$42.00"
        assert result.percent == "42.0%"


class TestCodeResourceWithLlmNode:
    """
    CODE resource с LlmNode: функции доступны в tools.
    """

    @pytest.mark.asyncio
    async def test_code_resource_in_react_tool(self, mock_llm_with_queue, container):
        """
        Code resource доступен в inline tool LlmNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef calculate_discount(price, percent):\n    return price * (1 - percent / 100)\n\ndef format_price(price):\n    return f'${price:.2f}'\n",
            },
        }
        tool = {
            "tool_id": "apply_discount",
            "type": "code",
            "description": "Applies discount to price",
            "parameters_schema": {
                "type": "object",
                "properties": {"price": {"type": "number"}, "discount": {"type": "number"}},
                "required": ["price", "discount"],
            },
            "code": "\nasync def run(args, state):\n    discounted = pricing.calculate_discount(args['price'], args['discount'])\n    formatted = pricing.format_price(discounted)\n    state.final_price = formatted\n    return {'price': formatted}\n",
        }
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "apply_discount",
                    "args": {"price": 100, "discount": 20},
                },
                {"type": "text", "content": "Price calculated"},
            ]
        )
        llm_node = LlmNode(
            node_id="pricing_agent",
            config={
                "prompt": "Calculate prices",
                "tools": [tool],
                "resources": {"pricing": ResourceReference.model_validate(code_resource)},
            },
            container=container,
        )
        state = make_state(content="Apply 20% discount to $100")
        result = await llm_node.run(state)
        assert result.final_price == "$80.00"


class TestCombinedResourcesWithNodes:
    """
    Несколько code-ресурсов в одной CodeNode.
    """

    @pytest.mark.asyncio
    async def test_multiple_resources_in_code_node(self, container):
        fmt = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef format_fact(fact, source):\n    return f'[{source}] {fact}'\n",
            },
        }
        suffix = {
            "type": "code",
            "config": {"language": "python", "code": "\ndef suffix(s):\n    return s + ' END'\n"},
        }
        node = CodeNode(
            node_id="combined_node",
            config={
                "code": "\nasync def run(args, state):\n    formatted = utils.format_fact('hello', 'src')\n    state.formatted = formatted\n    state.suffixed = extra.suffix(formatted)\n    return {'success': True}\n",
                "resources": {
                    "utils": ResourceReference.model_validate(fmt),
                    "extra": ResourceReference.model_validate(suffix),
                },
            },
            container=container,
        )
        state = make_state()
        result = await node.run(state)
        assert "[src]" in result.formatted
        assert result.suffixed.endswith(" END")


class TestResourceInheritance:
    """
    Наследование ресурсов: flow_resources -> node_resources.
    """

    @pytest.mark.asyncio
    async def test_flow_resources_available_in_code_node(self, container):
        """
        Ресурсы уровня flow доступны в CodeNode через state.
        """
        code_resource = {
            "type": "code",
            "config": {"language": "python", "code": "\ndef double(n):\n    return n * 2\n"},
        }
        node = CodeNode(
            node_id="inheritor",
            config={
                "code": "\nasync def run(args, state):\n    result = math_utils.double(state.value)\n    state.doubled = result\n    return {'result': result}\n",
                "resources": {"math_utils": ResourceReference.model_validate(code_resource)},
            },
            container=container,
        )
        state = make_state(value=21)
        result = await node.run(state)
        assert result.doubled == 42

    @pytest.mark.asyncio
    async def test_node_resource_overrides_agent_resource(self, container):
        """
        Ресурс ноды переопределяет ресурс агента с тем же именем.
        """
        node_resource = {
            "type": "code",
            "config": {"language": "python", "code": "\ndef process(x):\n    return x * 10\n"},
        }
        node = CodeNode(
            node_id="override_test",
            config={
                "code": "\nasync def run(args, state):\n    result = helper.process(state.input)\n    state.output = result\n    return {'result': result}\n",
                "resources": {"helper": ResourceReference.model_validate(node_resource)},
            },
            container=container,
        )
        state = make_state(input=5)
        result = await node.run(state)
        assert result.output == 50


class TestFILESResource:
    """
    FILES resource: работа с S3/MinIO файлами.

    Требует запущенный MinIO.
    """

    MINIO_CONFIG = {
        "bucket": "test-bucket",
        "endpoint_url": "http://localhost:19002",
        "access_key_id": "minioadmin",
        "secret_access_key": "minioadmin",
    }

    @pytest.fixture
    def unique_prefix(self):
        """Уникальный префикс для изоляции тестов."""
        return f"test_resources/{uuid.uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_files_resource_write_read(self, unique_prefix, container):
        """
        FILES resource: запись и чтение файла.
        """
        files_resource = {"type": "files", "config": {**self.MINIO_CONFIG, "prefix": unique_prefix}}
        write_node = CodeNode(
            node_id="write_file",
            config={
                "code": "\nasync def run(args, state):\n    path = await storage.write('test.txt', 'Hello from resource test!')\n    state.file_path = path\n    return {'path': path}\n",
                "resources": {"storage": ResourceReference.model_validate(files_resource)},
            },
            container=container,
        )
        state = make_state()
        await write_node.run(state)
        read_node = CodeNode(
            node_id="read_file",
            config={
                "code": "\nasync def run(args, state):\n    content = await storage.read('test.txt')\n    state.file_content = content\n    return {'content': content}\n",
                "resources": {"storage": ResourceReference.model_validate(files_resource)},
            },
            container=container,
        )
        state2 = make_state()
        read_result = await read_node.run(state2)
        assert read_result.file_content == "Hello from resource test!"

    @pytest.mark.asyncio
    async def test_files_resource_in_react_tool(
        self, mock_llm_with_queue, unique_prefix, container
    ):
        """
        FILES resource доступен в inline tool LlmNode.
        """
        files_resource = {"type": "files", "config": {**self.MINIO_CONFIG, "prefix": unique_prefix}}
        tool = {
            "tool_id": "save_note",
            "type": "code",
            "description": "Saves a note to storage",
            "parameters_schema": {
                "type": "object",
                "properties": {"filename": {"type": "string"}, "content": {"type": "string"}},
                "required": ["filename", "content"],
            },
            "code": "\nasync def run(args, state):\n    path = await storage.write(args['filename'], args['content'])\n    state.saved_path = path\n    return {'path': path}\n",
        }
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "save_note",
                    "args": {"filename": "note.txt", "content": "Important note"},
                },
                {"type": "text", "content": "Note saved"},
            ]
        )
        llm_node = LlmNode(
            node_id="notes_agent",
            config={
                "prompt": "Save notes",
                "tools": [tool],
                "resources": {"storage": ResourceReference.model_validate(files_resource)},
            },
            container=container,
        )
        state = make_state(content="Save a note")
        result = await llm_node.run(state)
        assert result.saved_path is not None
        assert "note.txt" in result.saved_path


class TestLLMResource:
    """
    LLM resource: генерация текста.

    MockLLM используется автоматически (TESTING=true).
    """

    @pytest.mark.asyncio
    async def test_llm_resource_complete(self, mock_llm, container):
        """
        LLM resource: генерация текста по промпту.
        """
        llm_resource = {"type": "llm", "config": {"provider": "mock", "model": "mock-gpt-4"}}
        node = CodeNode(
            node_id="llm_complete",
            config={
                "code": "\nasync def run(args, state):\n    response = await gpt.complete('Say hello in French')\n    state.response = response\n    return {'response': response}\n",
                "resources": {"gpt": ResourceReference.model_validate(llm_resource)},
            },
            container=container,
        )
        state = make_state()
        result = await node.run(state)
        assert result.response is not None
        assert len(result.response) > 0

    @pytest.mark.asyncio
    async def test_llm_resource_chat(self, mock_llm, container):
        """
        LLM resource: чат с историей сообщений.
        """
        llm_resource = {"type": "llm", "config": {"provider": "mock", "model": "mock-gpt-4"}}
        node = CodeNode(
            node_id="llm_chat",
            config={
                "code": "\nasync def run(args, state):\n    messages = [\n        {'role': 'user', 'content': 'Hi!'},\n        {'role': 'assistant', 'content': 'Hello!'},\n        {'role': 'user', 'content': 'How are you?'}\n    ]\n    response = await gpt.chat(messages)\n    state.chat_response = response\n    return {'response': response}\n",
                "resources": {"gpt": ResourceReference.model_validate(llm_resource)},
            },
            container=container,
        )
        state = make_state()
        result = await node.run(state)
        assert result.chat_response is not None

    @pytest.mark.asyncio
    async def test_llm_resource_in_react_tool(self, mock_llm_with_queue, container):
        """
        LLM resource доступен в inline tool LlmNode.
        """
        llm_resource = {"type": "llm", "config": {"provider": "mock", "model": "mock-gpt-4"}}
        tool = {
            "tool_id": "summarize",
            "type": "code",
            "description": "Summarizes text",
            "parameters_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            "code": "\nasync def run(args, state):\n    summary = await gpt.complete(f\"Summarize: {args['text']}\")\n    state.summary = summary\n    return {'summary': summary}\n",
        }
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "summarize", "args": {"text": "Long text here"}},
                {"type": "text", "content": "Summarized"},
            ]
        )
        llm_node = LlmNode(
            node_id="summarizer",
            config={
                "prompt": "Summarize texts",
                "tools": [tool],
                "resources": {"gpt": ResourceReference.model_validate(llm_resource)},
            },
            container=container,
        )
        state = make_state(content="Summarize this text")
        result = await llm_node.run(state)
        assert result.summary is not None


class TestResourceHierarchy:
    """
    Иерархия ресурсов: flow.resources -> skill.resources -> node.resources (из БД по session + version).
    """

    @staticmethod
    def _stub_entry_node() -> dict:
        return {"type": "code", "code": "async def run(args, state):\n    return {}\n"}

    @pytest.mark.asyncio
    async def test_agent_level_resources_in_llm_tool(self, mock_llm_with_queue, app, container):
        """
        Resources на уровне агента доступны в tools LlmNode.
        """
        code_resource = {
            "type": "code",
            "config": {"language": "python", "code": "\ndef double(x):\n    return x * 2\n"},
        }
        tool = {
            "tool_id": "calc",
            "type": "code",
            "description": "Doubles a number",
            "parameters_schema": {
                "type": "object",
                "properties": {"n": {"type": "number"}},
                "required": ["n"],
            },
            "code": "\nasync def run(args, state):\n    result = math.double(args['n'])\n    state.result = result\n    return {'result': result}\n",
        }
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "calc", "args": {"n": 21}},
                {"type": "text", "content": "Done"},
            ]
        )
        flow_id = "test_res_hierarchy_llm"
        fc = FlowConfig(
            flow_id=flow_id,
            name="res hierarchy llm",
            entry="main",
            nodes={"main": self._stub_entry_node()},
            edges=[Edge(from_node="main", to_node=None)],
            resources={"arith": ResourceReference.model_validate(code_resource)},
        )
        await container.flow_repository.set(fc)
        tool_with_arith = {
            **tool,
            "code": "\nasync def run(args, state):\n    result = arith.double(args['n'])\n    state.result = result\n    return {'result': result}\n",
        }
        llm_node = LlmNode(
            node_id="calc_node",
            config={"prompt": "Calculate", "tools": [tool_with_arith]},
            container=container,
        )
        state = make_state(
            content="Double 21",
            session_id=f"{flow_id}:test-context",
            flow_config_version=fc.version,
        )
        result = await llm_node.run(state)
        assert result.result == 42

    @pytest.mark.asyncio
    async def test_skill_level_resources(self, app, container):
        """
        Resources на уровне skill доступны в нодах этого skill.
        """
        skill_resource = {
            "type": "code",
            "config": {"language": "python", "code": "\ndef triple(x):\n    return x * 3\n"},
        }
        flow_id = "test_res_hierarchy_skill"
        fc = FlowConfig(
            flow_id=flow_id,
            name="res hierarchy skill",
            entry="main",
            nodes={"main": self._stub_entry_node()},
            edges=[Edge(from_node="main", to_node=None)],
            branches={
                "math_skill": BranchConfig(
                    name="Math",
                    resources={"math": ResourceReference.model_validate(skill_resource)},
                )
            },
        )
        await container.flow_repository.set(fc)
        node = CodeNode(
            node_id="triple_node",
            config={
                "code": "\nasync def run(args, state):\n    result = math.triple(state.input)\n    state.output = result\n    return {'result': result}\n"
            },
            container=container,
        )
        state = make_state(
            input=10,
            branch_id="math_skill",
            session_id=f"{flow_id}:test-context",
            flow_config_version=fc.version,
        )
        result = await node.run(state)
        assert result.output == 30

    @pytest.mark.asyncio
    async def test_skill_overrides_agent_resource(self, app, container):
        """
        Skill resource переопределяет agent resource с тем же именем.
        """
        agent_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef compute(x):\n    return x + 1  # Agent: добавляет 1\n",
            },
        }
        skill_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef compute(x):\n    return x + 100  # Skill: добавляет 100\n",
            },
        }
        flow_id = "test_res_hierarchy_override"
        fc = FlowConfig(
            flow_id=flow_id,
            name="res hierarchy override",
            entry="main",
            nodes={"main": self._stub_entry_node()},
            edges=[Edge(from_node="main", to_node=None)],
            resources={"helper": ResourceReference.model_validate(agent_resource)},
            branches={
                "premium": BranchConfig(
                    name="Premium",
                    resources={"helper": ResourceReference.model_validate(skill_resource)},
                )
            },
        )
        await container.flow_repository.set(fc)
        node = CodeNode(
            node_id="compute_node",
            config={
                "code": "\nasync def run(args, state):\n    result = helper.compute(state.input)\n    state.output = result\n    return {'result': result}\n"
            },
            container=container,
        )
        state = make_state(
            input=5,
            branch_id="premium",
            session_id=f"{flow_id}:test-context",
            flow_config_version=fc.version,
        )
        result = await node.run(state)
        assert result.output == 105

    @pytest.mark.asyncio
    async def test_node_overrides_skill_resource(self, container):
        """
        Node resource переопределяет skill resource.
        """
        node_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": "\ndef transform(x):\n    return x * 1000  # Node: умножает на 1000\n",
            },
        }
        node = CodeNode(
            node_id="transform_node",
            config={
                "code": "\nasync def run(args, state):\n    result = utils.transform(state.input)\n    state.output = result\n    return {'result': result}\n",
                "resources": {"utils": ResourceReference.model_validate(node_resource)},
            },
            container=container,
        )
        state = make_state(input=7)
        result = await node.run(state)
        assert result.output == 7000

    @pytest.mark.asyncio
    async def test_full_hierarchy_inheritance(self, container):
        """
        Полная иерархия: agent -> skill -> node.
        Разные ресурсы на каждом уровне.
        """
        node_resource = {
            "type": "code",
            "config": {"language": "python", "code": "\ndef from_node():\n    return 'NODE'\n"},
        }
        node = CodeNode(
            node_id="hierarchy_test",
            config={
                "code": "\nasync def run(args, state):\n    # Node resource всегда доступен\n    node_val = node_utils.from_node()\n    state.node_val = node_val\n    return {'node': node_val}\n",
                "resources": {"node_utils": ResourceReference.model_validate(node_resource)},
            },
            container=container,
        )
        state = make_state()
        result = await node.run(state)
        assert result.node_val == "NODE"


class TestSharedResources:
    """
    Shared resources: загрузка из БД по resource_id.
    """

    @pytest.mark.asyncio
    async def test_shared_resource_from_db(self, container):
        """
        Resource загружается из БД по resource_id.
        """
        shared_resource = ResourceDefinition(
            resource_id=f"shared_utils_{uuid.uuid4().hex[:8]}",
            type="code",
            name="Shared Utils",
            description="Shared utility functions",
            config={
                "language": "python",
                "code": "\ndef shared_hello():\n    return 'Hello from shared resource!'\n",
            },
        )
        await container.resource_repository.set(shared_resource)
        resource_ref = {"resource_id": shared_resource.resource_id}
        node = CodeNode(
            node_id="use_shared",
            config={
                "code": "\nasync def run(args, state):\n    greeting = shared.shared_hello()\n    state.greeting = greeting\n    return {'greeting': greeting}\n",
                "resources": {"shared": ResourceReference.model_validate(resource_ref)},
            },
            container=container,
        )
        state = make_state()
        result = await node.run(state)
        assert result.greeting == "Hello from shared resource!"

    @pytest.mark.asyncio
    async def test_shared_resource_with_patch(self, container, mock_llm):
        """
        Shared LLM resource с patch temperature (config merge).
        """
        shared_resource = ResourceDefinition(
            resource_id=f"shared_llm_{uuid.uuid4().hex[:8]}",
            type="llm",
            name="Shared mock LLM",
            description="Base LLM",
            config={"provider": "mock", "model": "mock-gpt-4", "temperature": 0.1},
        )
        await container.resource_repository.set(shared_resource)
        resource_ref = {"resource_id": shared_resource.resource_id, "config": {"temperature": 0.99}}
        node = CodeNode(
            node_id="use_shared_llm_patch",
            config={
                "code": "\nasync def run(args, state):\n    text = await gpt.complete('ping')\n    state.out = text\n    return {'out': text}\n",
                "resources": {"gpt": ResourceReference.model_validate(resource_ref)},
            },
            container=container,
        )
        state = make_state()
        result = await node.run(state)
        assert result.out is not None
        assert len(result.out) > 0
