"""
Тесты Markdown форматирования в заметках.

User Story: Форматирование текста как в markdown для читабельности заметок.
"""

import pytest


class TestMarkdownFormatting:
    """Поддержка Markdown в description"""
    
    @pytest.mark.asyncio
    async def test_markdown_in_description(self, crm_client, unique_id, auth_headers_system):
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
            "description": markdown_text
        }, headers=auth_headers_system)
        assert response.status_code == 200
        entity_id = response.json()["entity_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved = get_resp.json()
        assert retrieved["description"] == markdown_text
    
    @pytest.mark.asyncio
    async def test_markdown_with_links(self, crm_client, unique_id, auth_headers_system):
        """Markdown ссылки сохраняются"""
        markdown_text = """Полезные ссылки:
- [Документация](https://docs.example.com)
- [GitHub](https://github.com/example/repo)
- ![Диаграмма](https://example.com/diagram.png)"""
        
        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Заметка со ссылками {unique_id}",
            "description": markdown_text
        }, headers=auth_headers_system)
        entity_id = response.json()["entity_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved = get_resp.json()
        assert "[Документация]" in retrieved["description"]
        assert "https://docs.example.com" in retrieved["description"]
    
    @pytest.mark.asyncio
    async def test_markdown_tables(self, crm_client, unique_id, auth_headers_system):
        """Markdown таблицы сохраняются"""
        markdown_text = """| Задача | Исполнитель | Срок |
|--------|-------------|------|
| Дизайн | Иван | 10.01 |
| Разработка | Петр | 20.01 |
| Тестирование | Анна | 25.01 |"""
        
        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Заметка с таблицей {unique_id}",
            "description": markdown_text
        }, headers=auth_headers_system)
        entity_id = response.json()["entity_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved = get_resp.json()
        assert "| Задача |" in retrieved["description"]
        assert "Дизайн" in retrieved["description"]
    
    @pytest.mark.asyncio
    async def test_markdown_code_blocks(self, crm_client, unique_id, auth_headers_system):
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
            "description": markdown_text
        }, headers=auth_headers_system)
        entity_id = response.json()["entity_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved = get_resp.json()
        assert "```javascript" in retrieved["description"]
        assert "async function" in retrieved["description"]
        assert "```python" in retrieved["description"]
    
    @pytest.mark.asyncio
    async def test_markdown_mixed_formatting(self, crm_client, unique_id, auth_headers_system):
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
            "description": markdown_text
        }, headers=auth_headers_system)
        entity_id = response.json()["entity_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        retrieved = get_resp.json()
        assert "# Отчет о встрече" in retrieved["description"]
        assert "**Дата:**" in retrieved["description"]
        assert "> Важно" in retrieved["description"]

