"""
Тесты Markdown форматирования в заметках.

User Story: Форматирование текста как в markdown для читабельности заметок.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _entity_description(response: Response) -> str:
    return object_str(_http_json(response).get("description"), field="description")


class TestMarkdownFormatting:
    """Поддержка Markdown в description"""

    @pytest.mark.asyncio
    async def test_markdown_in_description(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Markdown сохраняется и возвращается без изменений"""
        markdown_text = """# Заголовок встречи

## Участники
- Иван Иванов
- Петр Петров

**Важно:** Обсудили проект X

### Договоренности
1. Начать разработку
2. Подготовить документацию
3. Провести тестирование

```python
def hello():
    print("world")
```

*Следующая встреча:* 15 января"""

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": "meeting",
            "name": f"Markdown заметка {unique_id}",
            "description": markdown_text,
        }, headers=auth_headers_system)
        assert response.status_code == 200
        entity_id = _entity_id(response)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved_description = _entity_description(get_resp)
        assert retrieved_description == markdown_text

    @pytest.mark.asyncio
    async def test_markdown_with_links(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Markdown ссылки сохраняются"""
        markdown_text = """Полезные ссылки:
- [Документация](https://docs.example.com)
- [GitHub](https://github.com/example/repo)
- ![Диаграмма](https://example.com/diagram.png)"""

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Заметка со ссылками {unique_id}",
            "description": markdown_text,
        }, headers=auth_headers_system)
        entity_id = _entity_id(response)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved_description = _entity_description(get_resp)
        assert "[Документация]" in retrieved_description
        assert "https://docs.example.com" in retrieved_description

    @pytest.mark.asyncio
    async def test_markdown_tables(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Markdown таблицы сохраняются"""
        markdown_text = """| Задача | Исполнитель | Срок |
|--------|-------------|------|
| Дизайн | Иван | 10.01 |
| Разработка | Петр | 20.01 |
| Тестирование | Анна | 25.01 |"""

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Заметка с таблицей {unique_id}",
            "description": markdown_text,
        }, headers=auth_headers_system)
        entity_id = _entity_id(response)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved_description = _entity_description(get_resp)
        assert "| Задача |" in retrieved_description
        assert "Дизайн" in retrieved_description

    @pytest.mark.asyncio
    async def test_markdown_code_blocks(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Блоки кода сохраняются"""
        markdown_text = """Пример кода:

```javascript
async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}
```

```python
import requests

def get_data():
    return requests.get("https://api.example.com", headers=auth_headers_system)
```"""

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Заметка с кодом {unique_id}",
            "description": markdown_text,
        }, headers=auth_headers_system)
        entity_id = _entity_id(response)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved_description = _entity_description(get_resp)
        assert "```javascript" in retrieved_description
        assert "async function" in retrieved_description
        assert "```python" in retrieved_description

    @pytest.mark.asyncio
    async def test_markdown_mixed_formatting(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Смешанное форматирование"""
        markdown_text = """# Отчет о встрече

**Дата:** 6 января 2024
**Участники:** *Иван*, *Петр*, *Анна*

## Обсуждение

1. **Проект A**
   - Завершен на 80%
   - Осталось: тестирование

2. **Проект B**
   - Только началwork
   - [Ссылка на задачи](https://tasks.example.com)

> Важно: Нужно ускорить разработку

---

Следующая встреча через неделю."""

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": "meeting",
            "name": f"Сложная заметка {unique_id}",
            "description": markdown_text,
        }, headers=auth_headers_system)
        entity_id = _entity_id(response)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved_description = _entity_description(get_resp)
        assert "# Отчет о встрече" in retrieved_description
        assert "**Дата:**" in retrieved_description
        assert "> Важно" in retrieved_description
