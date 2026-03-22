"""
Тесты для Vision Analyze Tool.
"""

import base64
import os
import tempfile

import pytest

from core.state import ExecutionState
from apps.flows.tools.ocr_document import vision_analyze, _vision_mock


class TestVisionAnalyzeTool:
    """Тесты vision_analyze."""

    @pytest.fixture
    def temp_image_file(self):
        """Создает временный файл с тестовыми данными."""
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_data)
            file_path = f.name
        
        yield file_path
        
        if os.path.exists(file_path):
            os.unlink(file_path)

    def test_tool_attributes(self):
        """Проверяет атрибуты tool."""
        assert vision_analyze.name == "vision_analyze"
        assert "vision" in vision_analyze.tags
        assert "ocr" in vision_analyze.tags
        assert "image" in vision_analyze.tags
        assert "Анализирует изображение" in vision_analyze.description

    def test_tool_parameters(self):
        """Проверяет схему параметров."""
        params = vision_analyze.parameters
        assert params["type"] == "object"
        assert "prompt" in params["properties"]
        assert "file_name" in params["properties"]
        assert "json_output" in params["properties"]
        assert "model" in params["properties"]
        assert "prompt" in params["required"]

    def test_mock_function(self):
        """Тестирует mock функцию."""
        result = _vision_mock({"prompt": "Извлеки текст"})
        
        assert result["success"] is True
        assert "result" in result
        assert "Mock vision result" in result["result"]
        assert "file_name" in result

    def test_mock_function_with_model(self):
        """Тестирует mock функцию с указанием модели."""
        result = _vision_mock({
            "prompt": "Найди данные",
            "model": "openai/gpt-4o",
        })
        
        assert result["success"] is True
        assert result["model"] == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_execute_no_files(self, unique_id):
        """Тестирует ошибку когда нет файлов."""
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[]
        )
        result = await vision_analyze.run(
            {"prompt": "Извлеки текст"},
            state=state,
        )
        
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_file_not_found_by_name(self, temp_image_file, unique_id):
        """Тестирует ошибку когда файл не найден по имени."""
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "doc.png",
                    "path": temp_image_file,
                    "mime_type": "image/png",
                    "size": 100,
                }
            ]
        )

        result = await vision_analyze.run(
            {"prompt": "Извлеки текст", "file_name": "missing.pdf"},
            state=state,
        )

        assert result["success"] is False
        assert "не найден" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_unsupported_mime(self, unique_id):
        """Тестирует ошибку для неподдерживаемого типа файла."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            file_path = f.name

        try:
            context_id = f"test-context-{unique_id}"
            state = ExecutionState(
                task_id=f"test-task-{unique_id}",
                context_id=context_id,
                user_id=f"test-user-{unique_id}",
                session_id=f"test-agent:{context_id}",
                files=[
                    {
                        "name": "doc.xyz",
                        "path": file_path,
                        "mime_type": "application/xyz",
                        "size": 4,
                    }
                ]
            )

            result = await vision_analyze.run(
                {"prompt": "Извлеки текст"},
                state=state,
            )

            assert result["success"] is False
            assert "Неподдерживаемый тип" in result["error"]
        finally:
            os.unlink(file_path)

    @pytest.mark.asyncio
    async def test_execute_file_path_not_exists(self, unique_id):
        """Тестирует ошибку когда файл не существует на диске."""
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "missing.png",
                    "path": "/tmp/nonexistent_file_12345.png",
                    "mime_type": "image/png",
                    "size": 100,
                }
            ]
        )

        result = await vision_analyze.run(
            {"prompt": "Извлеки текст"},
            state=state,
        )

        assert result["success"] is False
        assert "не найден" in result["error"]


class TestVisionAnalyzeIntegration:
    """Интеграционные тесты Vision Analyze."""

    @pytest.fixture
    def test_image_path(self):
        """Путь к тестовому изображению."""
        from pathlib import Path
        return Path(__file__).parent.parent / "image_text.png"

    @pytest.mark.asyncio
    async def test_file_reading(self, test_image_path, unique_id):
        """Тест что tool корректно читает файл и определяет mime type."""
        import mimetypes
        
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "image_text.png",
                    "path": str(test_image_path),
                    "mime_type": "image/png",
                    "size": test_image_path.stat().st_size,
                }
            ]
        )
        
        assert test_image_path.exists(), f"Тестовый файл не найден: {test_image_path}"
        
        mime_type, _ = mimetypes.guess_type(str(test_image_path))
        assert mime_type == "image/png"
        
        files = state.files
        assert len(files) == 1
        assert files[0]["name"] == "image_text.png"

    @pytest.mark.asyncio
    async def test_with_mock(self, test_image_path, unique_id):
        """Тест с mock режимом."""
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "image_text.png",
                    "path": str(test_image_path),
                    "mime_type": "image/png",
                    "size": test_image_path.stat().st_size,
                }
            ]
        )
        
        result = await vision_analyze.run(
            {"prompt": "Извлеки весь текст"},
            state=state,
        )

        assert result["success"] is True
        assert "Mock vision result" in result["result"]

    @pytest.mark.asyncio
    async def test_with_file_name(self, test_image_path, unique_id):
        """Тест с указанием имени файла."""
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "other.png",
                    "path": str(test_image_path),
                    "mime_type": "image/png",
                    "size": 100,
                },
                {
                    "name": "image_text.png",
                    "path": str(test_image_path),
                    "mime_type": "image/png",
                    "size": test_image_path.stat().st_size,
                }
            ]
        )
        
        result = await vision_analyze.run(
            {"prompt": "Извлеки текст", "file_name": "image_text.png"},
            state=state,
        )

        assert result["success"] is True
        assert result["file_name"] == "image_text.png"

    @pytest.mark.asyncio
    async def test_with_json_output_mock(self, test_image_path, unique_id):
        """Тест с json_output в mock режиме."""
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "image_text.png",
                    "path": str(test_image_path),
                    "mime_type": "image/png",
                    "size": test_image_path.stat().st_size,
                }
            ]
        )
        
        result = await vision_analyze.run(
            {"prompt": "Найди данные паспорта", "json_output": True},
            state=state,
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_with_custom_model_mock(self, test_image_path, unique_id):
        """Тест с кастомной моделью в mock режиме."""
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "image_text.png",
                    "path": str(test_image_path),
                    "mime_type": "image/png",
                    "size": test_image_path.stat().st_size,
                }
            ]
        )
        
        result = await vision_analyze.run(
            {
                "prompt": "Опиши изображение",
                "model": "google/gemini-2.5-pro-preview",
            },
            state=state,
        )

        assert result["success"] is True
        assert result["model"] == "google/gemini-2.5-pro-preview"

    @pytest.mark.asyncio
    async def test_real_vision_analyze(self, test_image_path, unique_id):
        """Тест с реальным вызовом API (пропускается если нет подходящего провайдера)."""
        from apps.flows.config import get_settings
        
        context_id = f"test-context-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"test-agent:{context_id}",
            files=[
                {
                    "name": "image_text.png",
                    "path": str(test_image_path),
                    "mime_type": "image/png",
                    "size": test_image_path.stat().st_size,
                }
            ]
        )
        
        assert test_image_path.exists(), f"Тестовый файл не найден: {test_image_path}"
        
        settings = get_settings()
        
        def is_valid_api_key(key: str) -> bool:
            """Проверяет что ключ не фейковый."""
            if not key:
                return False
            fake_patterns = ["fake", "test", "dummy", "mock", "placeholder"]
            return not any(p in key.lower() for p in fake_patterns)
        
        openai_key = settings.llm.openai.api_key if settings.llm.openai else None
        openrouter_key = settings.llm.openrouter.api_key if settings.llm.openrouter else None
        
        has_valid_key = is_valid_api_key(openai_key) or is_valid_api_key(openrouter_key)
        
        if not has_valid_key:
            pytest.skip("Нет валидного API ключа для vision - пропускаем реальный тест")
        
        result = await vision_analyze.run(
            {"prompt": "Извлеки весь текст с изображения"},
            state=state,
        )
        
        assert result.get("success") is True, f"Vision analyze не удался: {result.get('error')}"
        assert "result" in result
        
        recognized_text = result["result"]
        assert isinstance(recognized_text, str)
        assert len(recognized_text) > 0
        
        print(f"\nФайл: {test_image_path}")
        print(f"Распознано {len(recognized_text)} символов")
        print(f"Первые 500 символов:\n{recognized_text[:500]}")
