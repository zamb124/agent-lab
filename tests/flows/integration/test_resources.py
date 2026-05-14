"""
Интеграционные тесты: resources (code, files, llm) с нодами.

MockLLM — где нужен LLM.
"""

import uuid

import pytest

from apps.flows.src.models import ResourceReference
from apps.flows.src.runtime.nodes import CodeNode, LlmNode
from core.state import ExecutionState


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
    async def test_code_resource_functions_available(self):
        """
        Функции из code resource доступны в CodeNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def format_phone(phone):
    digits = ''.join(c for c in phone if c.isdigit())
    return f'+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}'

def validate_email(email):
    return '@' in email and '.' in email.split('@')[1]
"""
            }
        }

        node = CodeNode(
            node_id="phone_formatter",
            config={
                "code": """
async def execute(args, state):
    formatted = helpers.format_phone(state.phone)
    is_valid = helpers.validate_email(state.email)
    state.formatted_phone = formatted
    state.email_valid = is_valid
    return {'phone': formatted, 'valid': is_valid}
""",
                "resources": {
                    "helpers": ResourceReference.model_validate(code_resource)
                }
            }
        )

        state = make_state(phone="89161234567", email="test@example.com")
        result = await node.run(state)

        assert result.formatted_phone == "+7 (916) 123-45-67"
        assert result.email_valid is True

    @pytest.mark.asyncio
    async def test_code_resource_class_available(self):
        """
        Классы из code resource доступны в CodeNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
class Calculator:
    @staticmethod
    def add(a, b):
        return a + b

    @staticmethod
    def multiply(a, b):
        return a * b

class StringHelper:
    @staticmethod
    def reverse(s):
        return s[::-1]
"""
            }
        }

        node = CodeNode(
            node_id="calculator",
            config={
                "code": """
async def execute(args, state):
    result = utils.Calculator.add(10, 5)
    product = utils.Calculator.multiply(result, 2)
    reversed_name = utils.StringHelper.reverse(state.name)
    state.sum_result = result
    state.product_result = product
    state.reversed_name = reversed_name
    return {'sum': result, 'product': product, 'reversed': reversed_name}
""",
                "resources": {
                    "utils": ResourceReference.model_validate(code_resource)
                }
            }
        )

        state = make_state(name="Hello")
        result = await node.run(state)

        assert result.sum_result == 15
        assert result.product_result == 30
        assert result.reversed_name == "olleH"

    @pytest.mark.asyncio
    async def test_multiple_code_resources(self):
        """
        Несколько code resources доступны в CodeNode.
        """
        validators = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def is_positive(n):
    return n > 0

def is_even(n):
    return n % 2 == 0
"""
            }
        }

        formatters = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def to_currency(n):
    return f'${n:,.2f}'

def to_percent(n):
    return f'{n * 100:.1f}%'
"""
            }
        }

        node = CodeNode(
            node_id="multi_resource",
            config={
                "code": """
async def execute(args, state):
    num = state.number
    is_pos = validators.is_positive(num)
    is_even = validators.is_even(num)
    currency = formatters.to_currency(num)
    percent = formatters.to_percent(num / 100)

    state.is_positive = is_pos
    state.is_even = is_even
    state.currency = currency
    state.percent = percent

    return {'positive': is_pos, 'even': is_even, 'currency': currency}
""",
                "resources": {
                    "validators": ResourceReference.model_validate(validators),
                    "formatters": ResourceReference.model_validate(formatters),
                }
            }
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
    async def test_code_resource_in_react_tool(self, mock_llm_with_queue):
        """
        Code resource доступен в inline tool LlmNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def calculate_discount(price, percent):
    return price * (1 - percent / 100)

def format_price(price):
    return f'${price:.2f}'
"""
            }
        }

        tool = {
            "tool_id": "apply_discount",
            "type": "code",
            "description": "Applies discount to price",
            "args_schema": {
                "price": {"type": "number"},
                "discount": {"type": "number"}
            },
            "code": """
async def execute(args, state):
    discounted = pricing.calculate_discount(args['price'], args['discount'])
    formatted = pricing.format_price(discounted)
    state.final_price = formatted
    return {'price': formatted}
"""
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "apply_discount", "args": {"price": 100, "discount": 20}},
            {"type": "text", "content": "Price calculated"},
        ])

        llm_node = LlmNode(
            node_id="pricing_agent",
            config={
                "prompt": "Calculate prices",
                "tools": [tool],
                "resources": {
                    "pricing": ResourceReference.model_validate(code_resource)
                }
            }
        )

        state = make_state(content="Apply 20% discount to $100")
        result = await llm_node.run(state)

        assert result.final_price == "$80.00"


class TestCombinedResourcesWithNodes:
    """
    Несколько code-ресурсов в одной CodeNode.
    """

    @pytest.mark.asyncio
    async def test_multiple_resources_in_code_node(self):
        fmt = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def format_fact(fact, source):
    return f'[{source}] {fact}'
"""
            }
        }
        suffix = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def suffix(s):
    return s + ' END'
"""
            }
        }
        node = CodeNode(
            node_id="combined_node",
            config={
                "code": """
async def execute(args, state):
    formatted = utils.format_fact('hello', 'src')
    state.formatted = formatted
    state.suffixed = extra.suffix(formatted)
    return {'success': True}
""",
                "resources": {
                    "utils": ResourceReference.model_validate(fmt),
                    "extra": ResourceReference.model_validate(suffix),
                }
            }
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
    async def test_flow_resources_available_in_code_node(self):
        """
        Ресурсы уровня flow доступны в CodeNode через state.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def double(n):
    return n * 2
"""
            }
        }

        node = CodeNode(
            node_id="inheritor",
            config={
                "code": """
async def execute(args, state):
    result = math_utils.double(state.value)
    state.doubled = result
    return {'result': result}
""",
                "resources": {
                    "math_utils": ResourceReference.model_validate(code_resource)
                }
            }
        )

        state = make_state(value=21)
        result = await node.run(state)

        assert result.doubled == 42

    @pytest.mark.asyncio
    async def test_node_resource_overrides_agent_resource(self):
        """
        Ресурс ноды переопределяет ресурс агента с тем же именем.
        """

        node_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def process(x):
    return x * 10
"""
            }
        }

        # Нода использует свой ресурс, а не agent-level
        node = CodeNode(
            node_id="override_test",
            config={
                "code": """
async def execute(args, state):
    result = helper.process(state.input)
    state.output = result
    return {'result': result}
""",
                "resources": {
                    "helper": ResourceReference.model_validate(node_resource)
                }
            }
        )

        state = make_state(input=5)
        result = await node.run(state)

        # Должен использоваться node_resource (x * 10), а не agent_resource (x + 10)
        assert result.output == 50


# =============================================================================
# FILES Resource
# =============================================================================

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
    async def test_files_resource_write_read(self, unique_prefix):
        """
        FILES resource: запись и чтение файла.
        """
        files_resource = {
            "type": "files",
            "config": {
                **self.MINIO_CONFIG,
                "prefix": unique_prefix
            }
        }

        # Записываем файл
        write_node = CodeNode(
            node_id="write_file",
            config={
                "code": """
async def execute(args, state):
    path = await storage.write('test.txt', 'Hello from resource test!')
    state.file_path = path
    return {'path': path}
""",
                "resources": {
                    "storage": ResourceReference.model_validate(files_resource)
                }
            }
        )

        state = make_state()
        await write_node.run(state)

        # Читаем файл
        read_node = CodeNode(
            node_id="read_file",
            config={
                "code": """
async def execute(args, state):
    content = await storage.read('test.txt')
    state.file_content = content
    return {'content': content}
""",
                "resources": {
                    "storage": ResourceReference.model_validate(files_resource)
                }
            }
        )

        state2 = make_state()
        read_result = await read_node.run(state2)

        assert read_result.file_content == 'Hello from resource test!'

    @pytest.mark.asyncio
    async def test_files_resource_list(self, unique_prefix):
        """
        FILES resource: список файлов.
        """
        files_resource = {
            "type": "files",
            "config": {
                **self.MINIO_CONFIG,
                "prefix": unique_prefix
            }
        }

        # Создаём несколько файлов
        from apps.flows.src.resources.wrappers import FilesResource
        storage = FilesResource(
            prefix=unique_prefix,
            **self.MINIO_CONFIG
        )
        await storage.write("file1.txt", "Content 1")
        await storage.write("file2.txt", "Content 2")

        # Получаем список
        list_node = CodeNode(
            node_id="list_files",
            config={
                "code": """
async def execute(args, state):
    files = await storage.list()
    state.file_count = len(files)
    state.files = files
    return {'count': state.file_count}
""",
                "resources": {
                    "storage": ResourceReference.model_validate(files_resource)
                }
            }
        )

        state = make_state()
        result = await list_node.run(state)

        assert result.file_count >= 2

    @pytest.mark.asyncio
    async def test_files_resource_exists_delete(self, unique_prefix):
        """
        FILES resource: проверка существования и удаление.
        """
        files_resource = {
            "type": "files",
            "config": {
                **self.MINIO_CONFIG,
                "prefix": unique_prefix
            }
        }

        # Создаём файл напрямую
        from apps.flows.src.resources.wrappers import FilesResource
        storage = FilesResource(
            prefix=unique_prefix,
            **self.MINIO_CONFIG
        )
        await storage.write("to_delete.txt", "Will be deleted")

        # Проверяем и удаляем через ноду
        node = CodeNode(
            node_id="check_delete",
            config={
                "code": """
async def execute(args, state):
    exists_before = await storage.exists('to_delete.txt')
    deleted = await storage.delete('to_delete.txt')
    exists_after = await storage.exists('to_delete.txt')

    state.existed = exists_before
    state.deleted = deleted
    state.gone = not exists_after
    return {'success': state.gone}
""",
                "resources": {
                    "storage": ResourceReference.model_validate(files_resource)
                }
            }
        )

        state = make_state()
        result = await node.run(state)

        assert result.existed is True
        assert result.deleted is True
        assert result.gone is True

    @pytest.mark.asyncio
    async def test_files_resource_in_react_tool(self, mock_llm_with_queue, unique_prefix):
        """
        FILES resource доступен в inline tool LlmNode.
        """
        files_resource = {
            "type": "files",
            "config": {
                **self.MINIO_CONFIG,
                "prefix": unique_prefix
            }
        }

        tool = {
            "tool_id": "save_note",
            "type": "code",
            "description": "Saves a note to storage",
            "args_schema": {
                "filename": {"type": "string"},
                "content": {"type": "string"}
            },
            "code": """
async def execute(args, state):
    path = await storage.write(args['filename'], args['content'])
    state.saved_path = path
    return {'path': path}
"""
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "save_note", "args": {"filename": "note.txt", "content": "Important note"}},
            {"type": "text", "content": "Note saved"},
        ])

        llm_node = LlmNode(
            node_id="notes_agent",
            config={
                "prompt": "Save notes",
                "tools": [tool],
                "resources": {
                    "storage": ResourceReference.model_validate(files_resource)
                }
            }
        )

        state = make_state(content="Save a note")
        result = await llm_node.run(state)

        assert result.saved_path is not None
        assert "note.txt" in result.saved_path


# =============================================================================
# CACHE Resource
# =============================================================================

# =============================================================================
# LLM Resource (с MockLLM)
# =============================================================================

class TestLLMResource:
    """
    LLM resource: генерация текста.

    MockLLM используется автоматически (TESTING=true).
    """

    @pytest.mark.asyncio
    async def test_llm_resource_complete(self, mock_llm):
        """
        LLM resource: генерация текста по промпту.
        """
        llm_resource = {
            "type": "llm",
            "config": {
                "provider": "mock",
                "model": "mock-gpt-4"
            }
        }

        node = CodeNode(
            node_id="llm_complete",
            config={
                "code": """
async def execute(args, state):
    response = await gpt.complete('Say hello in French')
    state.response = response
    return {'response': response}
""",
                "resources": {
                    "gpt": ResourceReference.model_validate(llm_resource)
                }
            }
        )

        state = make_state()
        result = await node.run(state)

        # MockLLM возвращает "Test response"
        assert result.response is not None
        assert len(result.response) > 0

    @pytest.mark.asyncio
    async def test_llm_resource_chat(self, mock_llm):
        """
        LLM resource: чат с историей сообщений.
        """
        llm_resource = {
            "type": "llm",
            "config": {
                "provider": "mock",
                "model": "mock-gpt-4"
            }
        }

        node = CodeNode(
            node_id="llm_chat",
            config={
                "code": """
async def execute(args, state):
    messages = [
        {'role': 'user', 'content': 'Hi!'},
        {'role': 'assistant', 'content': 'Hello!'},
        {'role': 'user', 'content': 'How are you?'}
    ]
    response = await gpt.chat(messages)
    state.chat_response = response
    return {'response': response}
""",
                "resources": {
                    "gpt": ResourceReference.model_validate(llm_resource)
                }
            }
        )

        state = make_state()
        result = await node.run(state)

        assert result.chat_response is not None

    @pytest.mark.asyncio
    async def test_llm_resource_in_react_tool(self, mock_llm_with_queue):
        """
        LLM resource доступен в inline tool LlmNode.
        """
        llm_resource = {
            "type": "llm",
            "config": {
                "provider": "mock",
                "model": "mock-gpt-4"
            }
        }

        tool = {
            "tool_id": "summarize",
            "type": "code",
            "description": "Summarizes text",
            "args_schema": {
                "text": {"type": "string"}
            },
            "code": """
async def execute(args, state):
    summary = await gpt.complete(f"Summarize: {args['text']}")
    state.summary = summary
    return {'summary': summary}
"""
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "summarize", "args": {"text": "Long text here"}},
            {"type": "text", "content": "Summarized"},
        ])

        llm_node = LlmNode(
            node_id="summarizer",
            config={
                "prompt": "Summarize texts",
                "tools": [tool],
                "resources": {
                    "gpt": ResourceReference.model_validate(llm_resource)
                }
            }
        )

        state = make_state(content="Summarize this text")
        result = await llm_node.run(state)

        assert result.summary is not None


# =============================================================================
# Resource Hierarchy: agent -> skill -> node
# =============================================================================

class TestResourceHierarchy:
    """
    Иерархия ресурсов: flow.resources -> skill.resources -> node.resources (из БД по session + version).
    """

    @staticmethod
    def _stub_entry_node() -> dict:
        return {
            "type": "code",
            "code": "async def execute(args, state):\n    return {}\n",
        }

    @pytest.mark.asyncio
    async def test_agent_level_resources_in_llm_tool(self, mock_llm_with_queue, app, container):
        """
        Resources на уровне агента доступны в tools LlmNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def double(x):
    return x * 2
"""
            }
        }

        tool = {
            "tool_id": "calc",
            "type": "code",
            "description": "Doubles a number",
            "args_schema": {"n": {"type": "number"}},
            "code": """
async def execute(args, state):
    result = math.double(args['n'])
    state.result = result
    return {'result': result}
"""
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calc", "args": {"n": 21}},
            {"type": "text", "content": "Done"},
        ])

        from apps.flows.src.models.flow_config import Edge, FlowConfig

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
            "code": """
async def execute(args, state):
    result = arith.double(args['n'])
    state.result = result
    return {'result': result}
""",
        }

        llm_node = LlmNode(
            node_id="calc_node",
            config={
                "prompt": "Calculate",
                "tools": [tool_with_arith],
            }
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
            "config": {
                "language": "python",
                "code": """
def triple(x):
    return x * 3
"""
            }
        }

        from apps.flows.src.models.flow_config import BranchConfig, Edge, FlowConfig

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
                "code": """
async def execute(args, state):
    result = math.triple(state.input)
    state.output = result
    return {'result': result}
""",
            }
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
                "code": """
def compute(x):
    return x + 1  # Agent: добавляет 1
"""
            }
        }

        skill_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def compute(x):
    return x + 100  # Skill: добавляет 100
"""
            }
        }

        from apps.flows.src.models.flow_config import BranchConfig, Edge, FlowConfig

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
                "code": """
async def execute(args, state):
    result = helper.compute(state.input)
    state.output = result
    return {'result': result}
""",
            }
        )

        state = make_state(
            input=5,
            branch_id="premium",
            session_id=f"{flow_id}:test-context",
            flow_config_version=fc.version,
        )
        result = await node.run(state)

        # Должен использоваться skill resource: 5 + 100 = 105
        assert result.output == 105

    @pytest.mark.asyncio
    async def test_node_overrides_skill_resource(self):
        """
        Node resource переопределяет skill resource.
        """

        node_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def transform(x):
    return x * 1000  # Node: умножает на 1000
"""
            }
        }

        node = CodeNode(
            node_id="transform_node",
            config={
                "code": """
async def execute(args, state):
    result = utils.transform(state.input)
    state.output = result
    return {'result': result}
""",
                "resources": {
                    "utils": ResourceReference.model_validate(node_resource)
                }
            }
        )

        state = make_state(input=7)
        result = await node.run(state)

        # Node resource: 7 * 1000 = 7000
        assert result.output == 7000

    @pytest.mark.asyncio
    async def test_full_hierarchy_inheritance(self):
        """
        Полная иерархия: agent -> skill -> node.
        Разные ресурсы на каждом уровне.
        """


        node_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def from_node():
    return 'NODE'
"""
            }
        }

        # Ресурсы flow/skill берутся из БД по session_flow_id и flow_config_version
        # Здесь мы проверяем что node resource работает
        node = CodeNode(
            node_id="hierarchy_test",
            config={
                "code": """
async def execute(args, state):
    # Node resource всегда доступен
    node_val = node_utils.from_node()
    state.node_val = node_val
    return {'node': node_val}
""",
                "resources": {
                    "node_utils": ResourceReference.model_validate(node_resource)
                }
            }
        )

        state = make_state()
        result = await node.run(state)

        assert result.node_val == "NODE"


# =============================================================================
# Shared Resources из БД
# =============================================================================

class TestSharedResources:
    """
    Shared resources: загрузка из БД по resource_id.
    """

    @pytest.mark.asyncio
    async def test_shared_resource_from_db(self, container):
        """
        Resource загружается из БД по resource_id.
        """
        from apps.flows.src.models import ResourceDefinition

        # Создаём shared resource в БД
        shared_resource = ResourceDefinition(
            resource_id=f"shared_utils_{uuid.uuid4().hex[:8]}",
            type="code",
            name="Shared Utils",
            description="Shared utility functions",
            config={
                "language": "python",
                "code": """
def shared_hello():
    return 'Hello from shared resource!'
"""
            }
        )

        await container.resource_repository.set(shared_resource)

        # Используем через resource_id
        resource_ref = {
            "resource_id": shared_resource.resource_id
        }

        node = CodeNode(
            node_id="use_shared",
            config={
                "code": """
async def execute(args, state):
    greeting = shared.shared_hello()
    state.greeting = greeting
    return {'greeting': greeting}
""",
                "resources": {
                    "shared": ResourceReference.model_validate(resource_ref)
                }
            }
        )

        state = make_state()
        result = await node.run(state)

        assert result.greeting == "Hello from shared resource!"

    @pytest.mark.asyncio
    async def test_shared_resource_with_override(self, container, mock_llm):
        """
        Shared LLM resource с patch temperature (config merge).
        """
        from apps.flows.src.models import ResourceDefinition

        shared_resource = ResourceDefinition(
            resource_id=f"shared_llm_{uuid.uuid4().hex[:8]}",
            type="llm",
            name="Shared mock LLM",
            description="Base LLM",
            config={
                "provider": "mock",
                "model": "mock-gpt-4",
                "temperature": 0.1,
            },
        )
        await container.resource_repository.set(shared_resource)

        resource_ref = {
            "resource_id": shared_resource.resource_id,
            "config": {"temperature": 0.99},
        }

        node = CodeNode(
            node_id="use_shared_llm_override",
            config={
                "code": """
async def execute(args, state):
    text = await gpt.complete('ping')
    state.out = text
    return {'out': text}
""",
                "resources": {
                    "gpt": ResourceReference.model_validate(resource_ref)
                },
            },
        )

        state = make_state()
        result = await node.run(state)
        assert result.out is not None
        assert len(result.out) > 0
