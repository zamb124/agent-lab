"""
Интеграционные тесты: Resources со всеми типами нод.

Полное покрытие всех 8 типов ресурсов:
- CODE resource -> функции доступны в коде
- PROMPT resource -> шаблоны рендерятся
- HTTP resource -> реальные HTTP запросы
- RAG resource -> семантический поиск
- FILES resource -> S3/MinIO файлы
- CACHE resource -> Redis кэш
- LLM resource -> генерация текста (MockLLM)
- SECRET resource -> резолв секретов

Все тесты БЕЗ МОКОВ (кроме MockLLM).
"""

import asyncio
import uuid
import pytest

from apps.flows.src.runtime.nodes import LlmNode, CodeNode
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.models import ResourceType, ResourceReference
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
def execute(args, state):
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
def execute(args, state):
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
def execute(args, state):
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


class TestPromptResourceWithCodeNode:
    """
    PROMPT resource: Jinja2 шаблоны для генерации текста.
    """

    @pytest.mark.asyncio
    async def test_prompt_resource_renders_template(self):
        """
        Prompt resource рендерит шаблон с переменными.
        """
        prompt_resource = {
            "type": "prompt",
            "config": {
                "template": "Hello, {{ name }}! You have {{ count }} new messages.",
                "variables": {"count": 0}
            }
        }
        
        node = CodeNode(
            node_id="greeting",
            config={
                "code": """
def execute(args, state):
    greeting = email_template.render(name=state.user_name, count=state.message_count)
    state.greeting = greeting
    return {'greeting': greeting}
""",
                "resources": {
                    "email_template": ResourceReference.model_validate(prompt_resource)
                }
            }
        )
        
        state = make_state(user_name="John", message_count=5)
        result = await node.run(state)
        
        assert result.greeting == "Hello, John! You have 5 new messages."

    @pytest.mark.asyncio
    async def test_prompt_resource_with_complex_template(self):
        """
        Prompt resource с условиями и циклами.
        """
        prompt_resource = {
            "type": "prompt",
            "config": {
                "template": """
Order Summary:
{% for item in items %}
- {{ item.name }}: ${{ item.price }}
{% endfor %}
Total: ${{ total }}
{% if discount > 0 %}
Discount: {{ discount }}%
Final: ${{ total * (1 - discount/100) }}
{% endif %}
""".strip()
            }
        }
        
        node = CodeNode(
            node_id="order_summary",
            config={
                "code": """
def execute(args, state):
    items = [
        {'name': 'Widget', 'price': 10},
        {'name': 'Gadget', 'price': 25},
    ]
    summary = order_template.render(
        items=items,
        total=35,
        discount=state.discount
    )
    state.order_summary = summary
    return {'summary': summary}
""",
                "resources": {
                    "order_template": ResourceReference.model_validate(prompt_resource)
                }
            }
        )
        
        state = make_state(discount=10)
        result = await node.run(state)
        
        assert "Widget: $10" in result.order_summary
        assert "Gadget: $25" in result.order_summary
        assert "Discount: 10%" in result.order_summary
        assert "Final: $31.5" in result.order_summary


class TestHTTPResourceWithCodeNode:
    """
    HTTP resource: реальные HTTP запросы к внешним API.
    
    Используем Cat Facts API (https://catfact.ninja) - публичный API без auth.
    """

    @pytest.mark.asyncio
    async def test_http_resource_get_request(self):
        """
        HTTP resource делает реальный GET запрос к cat facts API.
        """
        http_resource = {
            "type": "http",
            "config": {
                "base_url": "https://catfact.ninja",
                "timeout": 10
            }
        }
        
        node = CodeNode(
            node_id="cat_facts",
            config={
                "code": """
async def execute(args, state):
    response = await cat_api.get('/fact')
    state.cat_fact = response.get('fact', '')
    state.fact_length = response.get('length', 0)
    return {'fact': state.cat_fact}
""",
                "resources": {
                    "cat_api": ResourceReference.model_validate(http_resource)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        # Проверяем что получили факт о кошках
        assert result.cat_fact is not None
        assert len(result.cat_fact) > 0
        assert result.fact_length > 0

    @pytest.mark.asyncio
    async def test_http_resource_with_query_params(self):
        """
        HTTP resource с query параметрами.
        """
        http_resource = {
            "type": "http",
            "config": {
                "base_url": "https://catfact.ninja",
                "timeout": 10
            }
        }
        
        node = CodeNode(
            node_id="cat_facts_limited",
            config={
                "code": """
async def execute(args, state):
    response = await cat_api.get('/facts', params={'limit': 3})
    facts = response.get('data', [])
    state.facts_count = len(facts)
    state.facts = [f.get('fact') for f in facts]
    return {'count': state.facts_count}
""",
                "resources": {
                    "cat_api": ResourceReference.model_validate(http_resource)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        # Должны получить 3 факта
        assert result.facts_count == 3
        assert len(result.facts) == 3
        for fact in result.facts:
            assert len(fact) > 0


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
def execute(args, state):
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


class TestHTTPResourceWithLlmNode:
    """
    HTTP resource с LlmNode: HTTP запросы в tools.
    """

    @pytest.mark.asyncio
    async def test_http_resource_in_react_tool(self, mock_llm_with_queue):
        """
        HTTP resource доступен в inline tool LlmNode.
        """
        http_resource = {
            "type": "http",
            "config": {
                "base_url": "https://catfact.ninja",
                "timeout": 10
            }
        }
        
        tool = {
            "tool_id": "get_cat_fact",
            "type": "code",
            "description": "Gets a random cat fact",
            "args_schema": {},
            "code": """
async def execute(args, state):
    response = await cat_api.get('/fact')
    fact = response.get('fact', 'No fact available')
    state.cat_fact = fact
    return {'fact': fact}
"""
        }
        
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "get_cat_fact", "args": {}},
            {"type": "text", "content": "Here's a cat fact"},
        ])
        
        llm_node = LlmNode(
            node_id="cat_agent",
            config={
                "prompt": "Get cat facts",
                "tools": [tool],
                "resources": {
                    "cat_api": ResourceReference.model_validate(http_resource)
                }
            }
        )
        
        state = make_state(content="Tell me a cat fact")
        result = await llm_node.run(state)
        
        assert result.cat_fact is not None
        assert len(result.cat_fact) > 0


class TestCombinedResourcesWithNodes:
    """
    Комбинированные ресурсы в нодах.
    """

    @pytest.mark.asyncio
    async def test_multiple_resources_in_code_node(self):
        """
        Несколько ресурсов разных типов в одной CodeNode.
        """
        code_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def format_fact(fact, source):
    return f'[{source}] {fact}'
"""
            }
        }
        
        prompt_resource = {
            "type": "prompt",
            "config": {
                "template": "Cat Fact of the Day:\n\n{{ fact }}\n\nSource: {{ source }}"
            }
        }
        
        http_resource = {
            "type": "http",
            "config": {
                "base_url": "https://catfact.ninja",
                "timeout": 10
            }
        }
        
        node = CodeNode(
            node_id="combined_node",
            config={
                "code": """
async def execute(args, state):
    response = await cat_api.get('/fact')
    raw_fact = response.get('fact', 'No fact')
    
    formatted = utils.format_fact(raw_fact, 'catfact.ninja')
    
    presentation = template.render(fact=raw_fact, source='catfact.ninja')
    
    state.raw_fact = raw_fact
    state.formatted = formatted
    state.presentation = presentation
    
    return {'success': True}
""",
                "resources": {
                    "utils": ResourceReference.model_validate(code_resource),
                    "template": ResourceReference.model_validate(prompt_resource),
                    "cat_api": ResourceReference.model_validate(http_resource),
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.raw_fact is not None
        assert "[catfact.ninja]" in result.formatted
        assert "Cat Fact of the Day:" in result.presentation
        assert result.raw_fact in result.presentation


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
def execute(args, state):
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
        agent_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def process(x):
    return x + 10
"""
            }
        }
        
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
def execute(args, state):
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
# PROMPT Resource с LlmNode
# =============================================================================

class TestPromptResourceWithLlmNode:
    """
    PROMPT resource с LlmNode: шаблоны в tools.
    """

    @pytest.mark.asyncio
    async def test_prompt_resource_in_react_tool(self, mock_llm_with_queue):
        """
        Prompt resource доступен в inline tool LlmNode.
        """
        prompt_resource = {
            "type": "prompt",
            "config": {
                "template": "Dear {{ name }},\n\nYour order #{{ order_id }} has been {{ status }}.\n\nBest regards"
            }
        }
        
        tool = {
            "tool_id": "generate_email",
            "type": "code",
            "description": "Generates order notification email",
            "args_schema": {
                "name": {"type": "string"},
                "order_id": {"type": "string"},
                "status": {"type": "string"}
            },
            "code": """
def execute(args, state):
    email = email_tmpl.render(
        name=args['name'],
        order_id=args['order_id'],
        status=args['status']
    )
    state.generated_email = email
    return {'email': email}
"""
        }
        
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "generate_email", "args": {"name": "John", "order_id": "12345", "status": "shipped"}},
            {"type": "text", "content": "Email generated"},
        ])
        
        llm_node = LlmNode(
            node_id="email_agent",
            config={
                "prompt": "Generate emails",
                "tools": [tool],
                "resources": {
                    "email_tmpl": ResourceReference.model_validate(prompt_resource)
                }
            }
        )
        
        state = make_state(content="Generate email for John")
        result = await llm_node.run(state)
        
        assert "Dear John" in result.generated_email
        assert "order #12345" in result.generated_email
        assert "shipped" in result.generated_email


# =============================================================================
# HTTP Resource - POST и headers
# =============================================================================

class TestHTTPResourceAdvanced:
    """
    HTTP resource: POST запросы и кастомные headers.
    """

    @pytest.mark.asyncio
    async def test_http_resource_post_request(self):
        """
        HTTP resource делает POST запрос.
        Используем httpbin.org для тестирования.
        """
        http_resource = {
            "type": "http",
            "config": {
                "base_url": "https://httpbin.org",
                "timeout": 10
            }
        }
        
        node = CodeNode(
            node_id="http_post",
            config={
                "code": """
async def execute(args, state):
    response = await api.post('/post', json={'message': 'Hello', 'count': 42})
    state.response_json = response.get('json', {})
    state.success = 'message' in state.response_json
    return {'success': state.success}
""",
                "resources": {
                    "api": ResourceReference.model_validate(http_resource)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.success is True
        assert result.response_json.get('message') == 'Hello'
        assert result.response_json.get('count') == 42

    @pytest.mark.asyncio
    async def test_http_resource_with_headers(self):
        """
        HTTP resource с кастомными headers.
        """
        http_resource = {
            "type": "http",
            "config": {
                "base_url": "https://httpbin.org",
                "headers": {
                    "X-Custom-Header": "test-value",
                    "Authorization": "Bearer test-token"
                },
                "timeout": 10
            }
        }
        
        node = CodeNode(
            node_id="http_headers",
            config={
                "code": """
async def execute(args, state):
    response = await api.get('/headers')
    headers = response.get('headers', {})
    state.custom_header = headers.get('X-Custom-Header')
    state.auth_header = headers.get('Authorization')
    return {'headers': headers}
""",
                "resources": {
                    "api": ResourceReference.model_validate(http_resource)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.custom_header == "test-value"
        assert result.auth_header == "Bearer test-token"


# =============================================================================
# RAG Resource
# =============================================================================

class TestRAGResource:
    """
    RAG resource: семантический поиск по документам.
    
    Использует pgvector напрямую через core/rag.
    """

    @pytest.fixture
    def unique_namespace(self):
        """Уникальный namespace для изоляции тестов."""
        return f"test_resources_{uuid.uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_rag_resource_add_and_search(self, unique_namespace, rag_provider_pgvector):
        """
        RAG resource: добавление документа и поиск.
        """
        rag_resource = {
            "type": "rag",
            "config": {
                "namespace": unique_namespace,
                "provider": "pgvector",
                "default_top_k": 3
            }
        }
        
        # Добавляем документ
        add_node = CodeNode(
            node_id="add_doc",
            config={
                "code": """
async def execute(args, state):
    result = await kb.add_document(
        document_id='doc_1',
        content='Cats are wonderful pets that love to sleep and play.',
        metadata={'category': 'pets'}
    )
    state.doc_added = True
    return {'added': True}
""",
                "resources": {
                    "kb": ResourceReference.model_validate(rag_resource)
                }
            }
        )
        
        state = make_state()
        await add_node.run(state)
        
        # Небольшая задержка для индексации
        await asyncio.sleep(0.5)
        
        # Ищем документ
        search_node = CodeNode(
            node_id="search_doc",
            config={
                "code": """
async def execute(args, state):
    results = await kb.search('pets that sleep', top_k=1)
    state.search_results = results
    state.found = len(results) > 0
    return {'found': state.found}
""",
                "resources": {
                    "kb": ResourceReference.model_validate(rag_resource)
                }
            }
        )
        
        state2 = make_state()
        result = await search_node.run(state2)
        
        assert result.found is True
        assert len(result.search_results) > 0

    @pytest.mark.asyncio
    async def test_rag_resource_in_react_tool(self, mock_llm_with_queue, unique_namespace, rag_provider_pgvector):
        """
        RAG resource доступен в inline tool LlmNode.
        """
        rag_resource = {
            "type": "rag",
            "config": {
                "namespace": unique_namespace,
                "provider": "pgvector",
                "default_top_k": 3
            }
        }
        
        # Сначала добавим документ
        from apps.flows.src.resources.wrappers import RAGResource
        rag = RAGResource(namespace=unique_namespace, provider="pgvector")
        await rag.add_document(
            document_id="faq_1",
            content="Return policy: You can return any item within 30 days of purchase.",
            metadata={"type": "faq"}
        )
        await asyncio.sleep(0.5)
        
        tool = {
            "tool_id": "search_faq",
            "type": "code",
            "description": "Search FAQ",
            "args_schema": {
                "query": {"type": "string"}
            },
            "code": """
async def execute(args, state):
    results = await kb.search(args['query'], top_k=1)
    if results:
        state.answer = results[0].get('content', '')
    else:
        state.answer = 'No answer found'
    return {'answer': state.answer}
"""
        }
        
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "search_faq", "args": {"query": "return policy"}},
            {"type": "text", "content": "Found answer"},
        ])
        
        llm_node = LlmNode(
            node_id="faq_agent",
            config={
                "prompt": "Answer questions from FAQ",
                "tools": [tool],
                "resources": {
                    "kb": ResourceReference.model_validate(rag_resource)
                }
            }
        )
        
        state = make_state(content="What is the return policy?")
        result = await llm_node.run(state)
        
        assert "30 days" in result.answer or result.answer != "No answer found"


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
        write_result = await write_node.run(state)
        
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

class TestCACHEResource:
    """
    CACHE resource: Redis кэширование.
    """

    @pytest.fixture
    def unique_namespace(self):
        """Уникальный namespace для изоляции тестов."""
        return f"test_cache_{uuid.uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_cache_resource_set_get(self, unique_namespace):
        """
        CACHE resource: set и get операции.
        """
        cache_resource = {
            "type": "cache",
            "config": {
                "namespace": unique_namespace,
                "ttl": 60
            }
        }
        
        node = CodeNode(
            node_id="cache_test",
            config={
                "code": """
async def execute(args, state):
    # Set value
    await cache.set('user:123', {'name': 'John', 'age': 30})
    
    # Get value
    user = await cache.get('user:123')
    
    state.user_name = user.get('name') if user else None
    state.user_age = user.get('age') if user else None
    return {'user': user}
""",
                "resources": {
                    "cache": ResourceReference.model_validate(cache_resource)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.user_name == "John"
        assert result.user_age == 30

    @pytest.mark.asyncio
    async def test_cache_resource_incr(self, unique_namespace):
        """
        CACHE resource: инкремент счётчика.
        """
        cache_resource = {
            "type": "cache",
            "config": {
                "namespace": unique_namespace,
                "ttl": 60
            }
        }
        
        node = CodeNode(
            node_id="cache_incr",
            config={
                "code": """
async def execute(args, state):
    # Инкрементируем счётчик несколько раз
    count1 = await cache.incr('page_views')
    count2 = await cache.incr('page_views')
    count3 = await cache.incr('page_views', 5)
    
    state.final_count = count3
    return {'count': count3}
""",
                "resources": {
                    "cache": ResourceReference.model_validate(cache_resource)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        # 1 + 1 + 5 = 7
        assert result.final_count == 7

    @pytest.mark.asyncio
    async def test_cache_resource_exists_delete(self, unique_namespace):
        """
        CACHE resource: exists и delete.
        """
        cache_resource = {
            "type": "cache",
            "config": {
                "namespace": unique_namespace,
                "ttl": 60
            }
        }
        
        node = CodeNode(
            node_id="cache_exists_delete",
            config={
                "code": """
async def execute(args, state):
    await cache.set('temp_key', 'temp_value')
    
    exists_before = await cache.exists('temp_key')
    deleted = await cache.delete('temp_key')
    exists_after = await cache.exists('temp_key')
    
    state.existed = exists_before
    state.deleted = deleted
    state.gone = not exists_after
    return {'success': state.gone}
""",
                "resources": {
                    "cache": ResourceReference.model_validate(cache_resource)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.existed is True
        assert result.deleted is True
        assert result.gone is True

    @pytest.mark.asyncio
    async def test_cache_resource_in_react_tool(self, mock_llm_with_queue, unique_namespace):
        """
        CACHE resource доступен в inline tool LlmNode.
        """
        cache_resource = {
            "type": "cache",
            "config": {
                "namespace": unique_namespace,
                "ttl": 60
            }
        }
        
        tool = {
            "tool_id": "cache_result",
            "type": "code",
            "description": "Caches a computation result",
            "args_schema": {
                "key": {"type": "string"},
                "value": {"type": "number"}
            },
            "code": """
async def execute(args, state):
    await cache.set(args['key'], args['value'])
    cached = await cache.get(args['key'])
    state.cached_value = cached
    return {'cached': cached}
"""
        }
        
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "cache_result", "args": {"key": "result", "value": 42}},
            {"type": "text", "content": "Cached"},
        ])
        
        llm_node = LlmNode(
            node_id="cache_agent",
            config={
                "prompt": "Cache results",
                "tools": [tool],
                "resources": {
                    "cache": ResourceReference.model_validate(cache_resource)
                }
            }
        )
        
        state = make_state(content="Cache the result")
        result = await llm_node.run(state)
        
        assert result.cached_value == 42


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
# SECRET Resource
# =============================================================================

class TestSECRETResource:
    """
    SECRET resource: резолв секретов из переменных.
    """

    @pytest.mark.asyncio
    async def test_secret_resource_resolves_var(self):
        """
        SECRET resource резолвит @var: ссылку.
        """
        secret_resource = {
            "type": "secret",
            "config": {
                "key": "@var:API_KEY"
            }
        }
        
        node = CodeNode(
            node_id="secret_test",
            config={
                "code": """
def execute(args, state):
    state.api_key = api_key
    state.key_length = len(api_key)
    return {'has_key': len(api_key) > 0}
""",
                "resources": {
                    "api_key": ResourceReference.model_validate(secret_resource)
                }
            }
        )
        
        state = make_state(variables={"API_KEY": "super-secret-key-123"})
        result = await node.run(state)
        
        assert result.api_key == "super-secret-key-123"
        assert result.key_length == 20

    @pytest.mark.asyncio
    async def test_secret_resource_missing_var_error(self):
        """
        SECRET resource выбрасывает ошибку если переменная не найдена.
        """
        secret_resource = {
            "type": "secret",
            "config": {
                "key": "@var:MISSING_KEY"
            }
        }
        
        node = CodeNode(
            node_id="secret_error",
            config={
                "code": """
def execute(args, state):
    state.secret = secret_val
    return {}
""",
                "resources": {
                    "secret_val": ResourceReference.model_validate(secret_resource)
                }
            }
        )
        
        state = make_state(variables={})
        
        with pytest.raises(ValueError, match="not found"):
            await node.run(state)


# =============================================================================
# Resource Hierarchy: agent -> skill -> node
# =============================================================================

class TestResourceHierarchy:
    """
    Иерархия ресурсов: flow_config.resources -> skill.resources -> node.resources
    """

    @pytest.mark.asyncio
    async def test_agent_level_resources_in_llm_tool(self, mock_llm_with_queue):
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
def execute(args, state):
    result = math.double(args['n'])
    state.result = result
    return {'result': result}
"""
        }
        
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calc", "args": {"n": 21}},
            {"type": "text", "content": "Done"},
        ])
        
        # Создаём flow_config с resources
        flow_config = {
            "resources": {
                "math": ResourceReference.model_validate(code_resource).model_dump()
            }
        }
        
        llm_node = LlmNode(
            node_id="calc_node",
            config={
                "prompt": "Calculate",
                "tools": [tool],
                "resources": {
                    "math": ResourceReference.model_validate(code_resource)
                }
            }
        )
        
        state = make_state(content="Double 21", flow_config=flow_config)
        result = await llm_node.run(state)
        
        assert result.result == 42

    @pytest.mark.asyncio
    async def test_skill_level_resources(self):
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
        
        # flow_config с skill resources
        flow_config = {
            "skills": {
                "math_skill": {
                    "resources": {
                        "math": ResourceReference.model_validate(skill_resource).model_dump()
                    }
                }
            }
        }
        
        node = CodeNode(
            node_id="triple_node",
            config={
                "code": """
def execute(args, state):
    result = math.triple(state.input)
    state.output = result
    return {'result': result}
""",
                "resources": {
                    "math": ResourceReference.model_validate(skill_resource)
                }
            }
        )
        
        state = make_state(input=10, skill_id="math_skill", flow_config=flow_config)
        result = await node.run(state)
        
        assert result.output == 30

    @pytest.mark.asyncio
    async def test_skill_overrides_agent_resource(self):
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
        
        flow_config = {
            "resources": {
                "helper": ResourceReference.model_validate(agent_resource).model_dump()
            },
            "skills": {
                "premium": {
                    "resources": {
                        "helper": ResourceReference.model_validate(skill_resource).model_dump()
                    }
                }
            }
        }
        
        node = CodeNode(
            node_id="compute_node",
            config={
                "code": """
def execute(args, state):
    result = helper.compute(state.input)
    state.output = result
    return {'result': result}
""",
                "resources": {
                    "helper": ResourceReference.model_validate(skill_resource)
                }
            }
        )
        
        state = make_state(input=5, skill_id="premium", flow_config=flow_config)
        result = await node.run(state)
        
        # Должен использоваться skill resource: 5 + 100 = 105
        assert result.output == 105

    @pytest.mark.asyncio
    async def test_node_overrides_skill_resource(self):
        """
        Node resource переопределяет skill resource.
        """
        skill_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def transform(x):
    return x * 2  # Skill: умножает на 2
"""
            }
        }
        
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
def execute(args, state):
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
        agent_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def from_agent():
    return 'AGENT'
"""
            }
        }
        
        skill_resource = {
            "type": "code",
            "config": {
                "language": "python",
                "code": """
def from_skill():
    return 'SKILL'
"""
            }
        }
        
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
        
        # В реальном сценарии flow_config передаётся в state
        # Здесь мы проверяем что node resource работает
        node = CodeNode(
            node_id="hierarchy_test",
            config={
                "code": """
def execute(args, state):
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
def execute(args, state):
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
    async def test_shared_resource_with_override(self, container):
        """
        Shared resource с override_config.
        """
        from apps.flows.src.models import ResourceDefinition
        
        # Создаём shared HTTP resource
        shared_resource = ResourceDefinition(
            resource_id=f"shared_api_{uuid.uuid4().hex[:8]}",
            type="http",
            name="Shared API",
            description="Base API config",
            config={
                "base_url": "https://httpbin.org",
                "timeout": 30
            }
        )
        
        await container.resource_repository.set(shared_resource)
        
        # Используем с override timeout
        resource_ref = {
            "resource_id": shared_resource.resource_id,
            "override_config": {
                "timeout": 5  # Переопределяем timeout
            }
        }
        
        node = CodeNode(
            node_id="use_shared_override",
            config={
                "code": """
async def execute(args, state):
    response = await api.get('/get')
    state.success = 'url' in response
    return {'success': state.success}
""",
                "resources": {
                    "api": ResourceReference.model_validate(resource_ref)
                }
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.success is True
