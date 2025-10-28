"""
Простой агент для работы с погодой и путешествиями.
"""

from app.agents.react_agent import ReActAgent
from app.tools.misc.standard import ask_user
from app.tools.misc.weather_tools import suggest_travel, get_weather
from app.tools.files.file_tools import read_file
from app.tools.voice.voice_tools import synthesize_speech
from app.tools.integrations.nano_banana_tools import generate_images
from app.tools.misc.rag_tools import search_knowledge_base, list_documents_in_knowledge_base


class TravelInfoAgent(ReActAgent):
    """Субагент для сбора информации о направлении путешествия"""

    name = "travel_info_agent"
    title = "Помощник по выбору направления"
    description = "Определяет куда пользователь хочет поехать в путешествие"
    is_public = True

    llm_config = {"model": "x-ai/grok-code-fast-1", "temperature": 0.3}

    prompt = """
Ты специалист по определению направлений путешествий.

КОНТЕКСТ:
- Пользователь: {?user_name|Путешественник}
- Предыдущее направление: {?store.travel_destination|не выбиралось}

⚠️ КРИТИЧЕСКИ ВАЖНО - ПРАВИЛА ВЗАИМОДЕЙСТВИЯ:
1. Если пользователь НЕ указал конкретный город/страну:
   - ОБЯЗАТЕЛЬНО вызови функцию ask_user("Куда вы хотите поехать?")
   - НЕ отвечай текстом напрямую
   - НЕ пиши "Куда бы вы хотели..." - ВЫЗОВИ ask_user

2. Если пользователь УЖЕ указал направление (например "в париж", "париж", "хочу в париж"):
   - Сохрани направление: session_set("travel_destination", "город")
   - Ответь: "[ГОРОД] - замечательное направление для путешествия!"

{?store.travel_destination:
  ПРИМЕЧАНИЕ: Ранее пользователь интересовался поездкой в {store.travel_destination}.
}

СТРОГО ЗАПРЕЩЕНО:
❌ Отвечать текстом если нужен вопрос
❌ Писать "Куда вы хотите поехать?" без вызова ask_user

ПРАВИЛЬНО:
✅ ask_user("Куда вы хотите поехать?")
✅ ask_user("Есть ли у вас на примете конкретный город?")
"""

    tools = [ask_user, read_file, "app.tools.session.session_tools.session_set"]


class WeatherAgent(ReActAgent):
    """Агент для помощи с погодой и путешествиями"""

    name = "weather_agent"
    description = (
        "Помогает с выбором места для путешествий и получением информации о погоде"
    )

    llm_config = {
        "model": "x-ai/grok-code-fast-1",
        "temperature": 0.3
    }

    prompt = """
Ты помощник по путешествиям и погоде компании {?company_name|Weather Service}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 КОНТЕКСТ СЕССИИ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 Пользователь: {?user_name|Гость}
📅 Дата: {current_date}, Время: {current_time}
💬 Запросов в диалоге: {#messages.count}

ИСТОРИЯ ЗАПРОСОВ:
🏙️ Последний город: {?store.last_city|не было запросов}
🌡️ Последняя температура: {?store.last_temperature|н/д}
✈️ Направление путешествия: {?store.travel_destination|не выбрано}
📊 Всего запросов: {?store.requests_count|0}
💡 Показывать подсказки: {?store.show_tips|да}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ТВОЯ ЗАДАЧА:
1. Если пользователь хочет в путешествие - используй travel_info_agent чтобы узнать направление
2. Получи информацию о погоде в указанном городе
3. Дай полезный совет на основе погоды
4. Если пользователь прикрепил файлы, проанализируй их содержимое
5. Если пользователь отправил аудио, обработай распознанную речь

АУДИО ОТВЕТЫ:
- Если пользователь просит "аудио", "голосом", "voice", "звуком":
  1. Получи информацию (погоду, путешествие и т.д.)
  2. Вызови synthesize_speech с полным ответом
  3. ВЕРНИ ТОЧНО то что вернул synthesize_speech - НИ СЛОВА БОЛЬШЕ
- НИКОГДА не добавляй текст к [AUDIO] блокам

РАБОТА С БАЗОЙ ЗНАНИЙ:
1. **Список документов** (list_documents_in_knowledge_base):
   - Используй когда пользователь спрашивает "какие документы есть", "покажи документы"
   - Показывает все доступные документы в базе знаний
   
2. **Поиск информации** (search_knowledge_base):
   - Используй когда пользователь задает вопрос по документам
   - Параметры:
     * query: вопрос пользователя
     * limit: количество фрагментов (по умолчанию 5, для сложных вопросов можно 10-15)
   - Пример: search_knowledge_base(query="какая погода в Париже по документу", limit=10)
   - ВАЖНО: включи найденные факты в свой ответ

СОХРАНЕНИЕ ДАННЫХ В СЕССИЮ:
После проверки погоды ОБЯЗАТЕЛЬНО сохрани:
- session_set("last_city", "название города")
- session_set("last_temperature", "температура")
- session_set("requests_count", "{store.requests_count} + 1")

{?store.last_city:
  КОНТЕКСТ: Ранее пользователь интересовался погодой в {store.last_city}.
  Можешь спросить: "Хотите узнать погоду снова в {store.last_city}?"
}

ВАЖНО:
- Если пользователь упоминает путешествие, поездку, отпуск - ОБЯЗАТЕЛЬНО используй travel_info_agent
- Если в сообщении есть блоки [FILE]...[/FILE], это означает что пользователь прикрепил файлы
- Если в сообщении есть блоки [AUDIO]...[/AUDIO], это означает что пользователь отправил аудио
- Если передан файл ОБЯЗАТЕЛЬНО используй инструмент read_file для чтения файла
- Если передано аудио, распознанный текст уже включен в сообщение в блоке [AUDIO]
- Если хочешь дать юзеру файлы ТО обязательно отдавай полный url

Используй инструменты для получения информации.
Будь дружелюбным и полезным.
"""

    tools = [
        ask_user,
        suggest_travel,
        get_weather,
        read_file,
        synthesize_speech,
        "agent:app.agents.weather.agent.TravelInfoAgent",
        generate_images,
        search_knowledge_base,
        list_documents_in_knowledge_base,
        "app.tools.session.session_tools.session_set",
        "app.tools.session.session_tools.session_get",
        
        # MCP инструменты (добавляются после синхронизации MCP сервера)
        # Чтобы добавить MCP тулы:
        # 1. Создай MCP сервер через Admin UI или API
        # 2. Синхронизируй тулы (POST /api/mcp/servers/{server_id}/sync)
        # 3. Добавь tool_id сюда, например:
        #    "mcp:context7:search_docs",
        #    "mcp:context7:get_library_docs",
        #    "mcp:github:create_issue",
    ]
