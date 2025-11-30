"""
Тесты для Telegram интерфейса.
Проверяет разбиение длинных сообщений и другие специфичные функции.
"""
import pytest
import pytest_asyncio
from apps.agents.interfaces.telegram_interface import TelegramInterface


class TestTelegramMessageSplitting:
    """Тесты разбиения длинных сообщений"""

    @pytest_asyncio.fixture
    async def telegram_interface(self):
        """Создает экземпляр TelegramInterface для тестов"""
        config = {
            "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "username": "test_bot"
        }
        return TelegramInterface(bot_token=config["token"], platform_config=config)

    def test_short_message_not_split(self, telegram_interface):
        """Короткие сообщения не разбиваются"""
        text = "Короткое сообщение"
        parts = telegram_interface._split_message(text)

        assert len(parts) == 1
        assert parts[0] == text

    def test_exact_limit_not_split(self, telegram_interface):
        """Сообщение ровно 4096 символов не разбивается"""
        text = "А" * 4096
        parts = telegram_interface._split_message(text)

        assert len(parts) == 1
        assert len(parts[0]) == 4096

    def test_long_message_split(self, telegram_interface):
        """Длинные сообщения разбиваются на части"""
        text = "А" * 5000
        parts = telegram_interface._split_message(text)

        assert len(parts) >= 2
        assert sum(len(p) for p in parts) >= len(text)

    def test_all_parts_within_limit(self, telegram_interface):
        """Все части сообщения не превышают лимит"""
        text = "А" * 10000
        parts = telegram_interface._split_message(text, max_length=4096)

        for part in parts:
            assert len(part) <= 4096, f"Часть превышает лимит: {len(part)} символов"

    def test_split_by_paragraphs(self, telegram_interface):
        """Разбиение происходит по абзацам если возможно"""
        # Создаем текст с абзацами
        paragraph1 = "A" * 2000
        paragraph2 = "B" * 2000
        paragraph3 = "C" * 2000
        text = f"{paragraph1}\n\n{paragraph2}\n\n{paragraph3}"

        parts = telegram_interface._split_message(text, max_length=4096)

        # Должно быть минимум 2 части
        assert len(parts) >= 2

        # Первая часть должна содержать первый и второй абзацы
        assert "A" in parts[0] and "B" in parts[0]

        # Вторая часть должна содержать третий абзац
        assert "C" in parts[-1]

    def test_split_preserves_content(self, telegram_interface):
        """Разбиение сохраняет весь контент"""
        text = "Первый абзац.\n\nВторой абзац.\n\nТретий абзац." * 500
        parts = telegram_interface._split_message(text, max_length=4096)

        # Объединяем все части
        combined = "".join(parts)

        # Проверяем что основной контент сохранился
        assert "Первый абзац" in combined
        assert "Второй абзац" in combined
        assert "Третий абзац" in combined

    def test_split_with_html_tags(self, telegram_interface):
        """Разбиение работает с HTML тегами"""
        text = "<b>Жирный текст</b> " * 1000 + "<i>Курсив</i> " * 1000
        parts = telegram_interface._split_message(text, max_length=4096)

        # Проверяем что HTML теги присутствуют в частях
        combined = "".join(parts)
        assert "<b>" in combined
        assert "</b>" in combined
        assert "<i>" in combined
        assert "</i>" in combined

    def test_split_by_sentences(self, telegram_interface):
        """Разбиение длинного абзаца по предложениям"""
        # Создаем очень длинный абзац из предложений
        sentence = "Это предложение номер X. " * 200
        text = sentence.replace("X", "1")

        parts = telegram_interface._split_message(text, max_length=4096)

        # Должно быть несколько частей
        assert len(parts) >= 2

        # Каждая часть не превышает лимит
        for part in parts:
            assert len(part) <= 4096

    def test_empty_message(self, telegram_interface):
        """Пустое сообщение возвращает пустую часть"""
        text = ""
        parts = telegram_interface._split_message(text)

        assert len(parts) == 1
        assert parts[0] == ""

    def test_message_with_newlines(self, telegram_interface):
        """Сообщение с множеством переносов строк"""
        text = "Строка\n" * 5000
        parts = telegram_interface._split_message(text, max_length=4096)

        # Проверяем что все части не превышают лимит
        for part in parts:
            assert len(part) <= 4096

        # Проверяем что переносы строк сохранились
        combined = "".join(parts)
        assert "\n" in combined

    def test_very_long_single_sentence(self, telegram_interface):
        """Очень длинное предложение без точек разбивается по символам"""
        text = "А" * 8000  # Одно "предложение" без точек
        parts = telegram_interface._split_message(text, max_length=4096)

        # Должно быть минимум 2 части
        assert len(parts) >= 2

        # Все части не превышают лимит
        for part in parts:
            assert len(part) <= 4096

    def test_custom_max_length(self, telegram_interface):
        """Тест с кастомным лимитом длины"""
        text = "А" * 1000
        parts = telegram_interface._split_message(text, max_length=100)

        # Должно быть много частей
        assert len(parts) >= 10

        # Все части не превышают кастомный лимит
        for part in parts:
            assert len(part) <= 100

    def test_realistic_message(self, telegram_interface):
        """Тест с реалистичным сообщением от агента"""
        text = """
# Добро пожаловать!

Я ваш AI-ассистент. Вот что я могу:

1. Отвечать на вопросы
2. Помогать с задачами
3. Предоставлять информацию

## Подробности

Для более детальной информации обратитесь к документации.
Я всегда рад помочь вам решить любые задачи.

""" * 200  # Повторяем чтобы превысить лимит

        parts = telegram_interface._split_message(text, max_length=4096)

        # Проверяем что разбиение произошло
        assert len(parts) >= 2

        # Все части не превышают лимит
        for part in parts:
            assert len(part) <= 4096

        # Основной контент сохранился
        combined = "".join(parts)
        assert "Добро пожаловать" in combined
        assert "AI-ассистент" in combined


class TestTelegramTypingIndicator:
    """Тесты для фонового индикатора печатания"""

    @pytest_asyncio.fixture
    async def telegram_interface(self):
        """Создает экземпляр TelegramInterface для тестов"""
        config = {
            "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "username": "test_bot"
        }
        return TelegramInterface(bot_token=config["token"], platform_config=config)

    @pytest.mark.asyncio
    async def test_typing_tasks_initialized(self, telegram_interface):
        """Проверяет что _typing_tasks инициализирован"""
        assert hasattr(telegram_interface, '_typing_tasks')
        assert isinstance(telegram_interface._typing_tasks, dict)
        assert len(telegram_interface._typing_tasks) == 0

    @pytest.mark.asyncio
    async def test_start_typing_indicator_creates_task(self, telegram_interface):
        """Проверяет что start_typing_indicator создает задачу"""
        session_id = "telegram:12345:flow:session"

        await telegram_interface.start_typing_indicator(session_id)

        # Задача должна быть создана
        assert session_id in telegram_interface._typing_tasks

        # Очищаем
        await telegram_interface.stop_typing_indicator(session_id)

    @pytest.mark.asyncio
    async def test_stop_typing_indicator_removes_task(self, telegram_interface):
        """Проверяет что stop_typing_indicator удаляет задачу"""
        session_id = "telegram:12345:flow:session"

        await telegram_interface.start_typing_indicator(session_id)
        assert session_id in telegram_interface._typing_tasks

        await telegram_interface.stop_typing_indicator(session_id)
        assert session_id not in telegram_interface._typing_tasks

    @pytest.mark.asyncio
    async def test_multiple_sessions_independent(self, telegram_interface):
        """Проверяет что несколько сессий работают независимо"""
        session1 = "telegram:11111:flow:session1"
        session2 = "telegram:22222:flow:session2"

        await telegram_interface.start_typing_indicator(session1)
        await telegram_interface.start_typing_indicator(session2)

        assert session1 in telegram_interface._typing_tasks
        assert session2 in telegram_interface._typing_tasks

        # Останавливаем первую сессию
        await telegram_interface.stop_typing_indicator(session1)

        assert session1 not in telegram_interface._typing_tasks
        assert session2 in telegram_interface._typing_tasks

        # Очищаем вторую
        await telegram_interface.stop_typing_indicator(session2)

