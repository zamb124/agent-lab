"""
Полные интеграционные тесты системы интернационализации
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from app.core.translation_manager import TranslationManager, get_translation_manager, t
from app.models.i18n_models import Language, I18nConfig
from app.models.context_models import Context
from app.identity.models import User, Company, AuthProvider, UserStatus


class TestFullI18nWorkflow:
    """Тесты полного workflow системы интернационализации"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
    
    @pytest.mark.asyncio
    async def test_startup_initialization_workflow(self):
        """Проверяем полный процесс инициализации при запуске"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Создаем тестовые файлы кода для сканирования
            test_dir = Path(temp_dir)
            
            # 1. Создаем тестовую Python модель
            models_dir = test_dir / "models"
            models_dir.mkdir()
            
            with open(models_dir / "test_model.py", "w") as f:
                f.write("""
from pydantic import BaseModel, Field

class TestModel(BaseModel):
    name: str = Field(title="Имя пользователя", description="Полное имя")
    email: str = Field(title="Email", placeholder="user@example.com")
""")
            
            # 2. Создаем тестовый HTML шаблон
            templates_dir = test_dir / "templates"
            templates_dir.mkdir()
            
            with open(templates_dir / "test.html", "w") as f:
                f.write("""
<html>
    <h1>{{ t('dashboard.title') }}</h1>
    <button>{{ t('common.save') }}</button>
</html>
""")
            
            # 3. Создаем тестовый JS файл
            js_dir = test_dir / "static"
            js_dir.mkdir()
            
            with open(js_dir / "test.js", "w") as f:
                f.write("""
app.i18n.t('common.loading');
const title = app.i18n.t('page.title');
""")
            
            # 4. Создаем менеджер с кастомной конфигурацией
            manager = TranslationManager()
            manager.config = I18nConfig(
                translations_directory=str(test_dir / "i18n"),
                scan_directories=[str(models_dir), str(templates_dir), str(js_dir)],
                auto_generate_on_startup=False  # Отключаем автогенерацию для контроля
            )
            manager.translations_dir = Path(manager.config.translations_directory)
            
            # 5. Запускаем только создание директорий и загрузку
            await manager._ensure_directories()
            await manager._load_translations()
            
            # 6. Вручную сканируем наши тестовые файлы
            await manager._scan_python_file(models_dir / "test_model.py")
            await manager._scan_html_file(templates_dir / "test.html")  
            await manager._scan_js_file(js_dir / "test.js")
            
            # 7. Проверяем что ключи найдены
            expected_keys = [
                "models.testmodel.fields.name.title",
                "models.testmodel.fields.name.description",
                "models.testmodel.fields.email.title",
                "models.testmodel.fields.email.placeholder"
            ]
            
            found_model_keys = 0
            for key in expected_keys:
                if key in manager._discovered_keys:
                    found_model_keys += 1
            
            # Проверяем что нашлись ключи из Python модели
            assert found_model_keys > 0
            
            # Проверяем что нашлись ключи из HTML
            html_keys = [key for key in manager._discovered_keys.keys() if any(k in key for k in ["dashboard.title", "common.save"])]
            assert len(html_keys) > 0
            
            # Проверяем что нашлись ключи из JS
            js_keys = [key for key in manager._discovered_keys.keys() if any(k in key for k in ["common.loading", "page.title"])]
            assert len(js_keys) > 0
            
            # 8. Создаем файлы переводов и JS модули
            if manager._discovered_keys:
                await manager._update_translation_files()
                await manager._generate_js_modules()
                
                # Проверяем что файлы переводов созданы
                ru_file = test_dir / "i18n" / "translations" / "ru.json"
                en_file = test_dir / "i18n" / "translations" / "en.json"
                
                assert ru_file.exists()
                assert en_file.exists()
                
                # 9. Проверяем JS модули
                ru_js = test_dir / "i18n" / "generated" / "ru.js"
                assert ru_js.exists()
                
                with open(ru_js) as f:
                    js_content = f.read()
                    assert "window.translations.ru" in js_content
                    
            else:
                # Если ключи не найдены, просто проверяем что директории созданы
                translations_dir = test_dir / "i18n" / "translations"
                assert translations_dir.exists()
    
    @pytest.mark.asyncio
    async def test_translation_update_workflow(self):
        """Проверяем workflow обновления переводов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TranslationManager()
            manager.config.translations_directory = str(Path(temp_dir) / "i18n")
            manager.translations_dir = Path(manager.config.translations_directory)
            
            await manager._ensure_directories()
            
            # 1. Создаем начальные переводы
            initial_keys = {
                "test.key1": {
                    "key": "test.key1", 
                    "default_value": "Тест 1",
                    "category": "test"
                },
                "test.key2": {
                    "key": "test.key2",
                    "default_value": "Тест 2", 
                    "category": "test"
                }
            }
            
            # Преобразуем в TranslationKey объекты
            from app.models.i18n_models import TranslationKey
            manager._discovered_keys = {
                key: TranslationKey(**data) for key, data in initial_keys.items()
            }
            
            # 2. Создаем первичные файлы
            await manager._update_translation_files()
            await manager._load_translations()
            
            # Проверяем что переводы загрузились
            assert "test.key1" in manager._translations_cache[Language.RU]
            assert manager._translations_cache[Language.RU]["test.key1"] == "Тест 1"
            
            # 3. Добавляем новые ключи
            manager._discovered_keys["test.key3"] = TranslationKey(
                key="test.key3",
                default_value="Тест 3",
                category="test"
            )
            
            # 4. Обновляем файлы
            await manager._update_translation_files()
            await manager._load_translations()
            
            # Проверяем что новый ключ добавился
            assert "test.key3" in manager._translations_cache[Language.RU]
            assert manager._translations_cache[Language.RU]["test.key3"] == "Тест 3"
            
            # Проверяем что старые ключи остались
            assert manager._translations_cache[Language.RU]["test.key1"] == "Тест 1"
    
    def test_end_to_end_translation_with_context(self):
        """Проверяем полный цикл перевода с контекстом"""
        # 1. Подготавливаем менеджер с тестовыми данными
        manager = get_translation_manager()
        manager._translations_cache = {
            Language.RU: {
                "welcome.message": "Добро пожаловать, {user_name}!",
                "dashboard.title": "Панель управления"
            },
            Language.EN: {
                "welcome.message": "Welcome, {user_name}!",
                "dashboard.title": "Dashboard"  
            }
        }
        
        # 2. Создаем контекст с английским языком
        mock_user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="John Doe",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        test_context = Context(
            user=mock_user,
            platform="api",
            active_company=None,
            user_companies=[],
            language=Language.EN
        )
        
        # 3. Тестируем перевод с контекстом
        with patch('app.core.translation_manager.get_context', return_value=test_context):
            result = t("dashboard.title")
            assert result == "Dashboard"
            
            result = t("welcome.message", user_name="John")
            assert result == "Welcome, John!"
        
        # 4. Тестируем fallback на русский для отсутствующего ключа
        with patch('app.core.translation_manager.get_context', return_value=test_context):
            manager._translations_cache[Language.RU]["ru.only.key"] = "Только на русском"
            result = t("ru.only.key")
            assert result == "Только на русском"


class TestTranslationFileOperations:
    """Тесты файловых операций с переводами"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
    
    @pytest.mark.asyncio
    async def test_translation_file_versioning(self):
        """Проверяем версионирование файлов переводов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TranslationManager()
            manager.config.translations_directory = str(Path(temp_dir) / "i18n")
            manager.translations_dir = Path(manager.config.translations_directory)
            
            await manager._ensure_directories()
            
            # Создаем файл с версией
            translations_file = manager.translations_dir / "translations" / "ru.json"
            initial_data = {
                "meta": {
                    "language": "ru",
                    "version": "1.0.0",
                    "last_updated": "2025-01-01T00:00:00Z",
                    "total_keys": 1,
                    "translated_keys": 1
                },
                "test": {"key": "Тест"}
            }
            
            with open(translations_file, 'w', encoding='utf-8') as f:
                json.dump(initial_data, f, ensure_ascii=False, indent=2)
            
            # Загружаем переводы
            await manager._load_translations()
            
            # Проверяем что загрузилось правильно
            assert "test.key" in manager._translations_cache[Language.RU]
            assert manager._translations_cache[Language.RU]["test.key"] == "Тест"
    
    @pytest.mark.asyncio
    async def test_missing_translation_file_creation(self):
        """Проверяем создание отсутствующих файлов переводов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TranslationManager()
            manager.config.translations_directory = str(Path(temp_dir) / "i18n")
            manager.translations_dir = Path(manager.config.translations_directory)
            
            await manager._ensure_directories()
            
            # Добавляем тестовый ключ
            from app.models.i18n_models import TranslationKey
            manager._discovered_keys = {
                "new.key": TranslationKey(
                    key="new.key",
                    default_value="Новый ключ",
                    category="test"
                )
            }
            
            # Обновляем файлы (должны создаться новые)
            await manager._update_translation_files()
            
            # Проверяем что файлы созданы
            for lang in Language:
                file_path = manager.translations_dir / "translations" / f"{lang.value}.json"
                assert file_path.exists()
                
                with open(file_path) as f:
                    data = json.load(f)
                    assert "meta" in data
                    assert data["meta"]["language"] == lang.value
                    
                    if lang == Language.RU:
                        assert data["new"]["key"] == "Новый ключ"
                    else:
                        assert data["new"]["key"] == "[TODO: new.key]"


class TestI18nPerformance:
    """Тесты производительности системы переводов"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
    
    def test_translation_caching(self):
        """Проверяем кеширование переводов"""
        manager = get_translation_manager()
        
        # Загружаем большой набор тестовых переводов
        large_translations = {}
        for i in range(1000):
            large_translations[f"test.key.{i}"] = f"Тест {i}"
        
        manager._translations_cache[Language.RU] = large_translations
        
        # Проверяем быстрое получение переводов
        import time
        start_time = time.time()
        
        for i in range(100):
            result = manager.t(f"test.key.{i % 100}", Language.RU)
            assert result == f"Тест {i % 100}"
        
        elapsed = time.time() - start_time
        
        # Проверяем что операции быстрые (меньше 1 секунды для 100 переводов)
        assert elapsed < 1.0
    
    def test_translation_memory_usage(self):
        """Проверяем использование памяти при множественных запросах"""
        manager = get_translation_manager()
        
        # Создаем умеренный набор переводов для всех языков
        test_translations = {}
        for lang in Language:
            test_translations[lang] = {}
            for i in range(100):
                test_translations[lang][f"key.{i}"] = f"Value {i} in {lang.value}"
        
        manager._translations_cache = test_translations
        
        # Проверяем что get_translations возвращает копию (не влияет на кеш)
        translations_copy = manager.get_translations(Language.RU)
        translations_copy["new.key"] = "Modified"
        
        # Оригинальный кеш не должен измениться
        assert "new.key" not in manager._translations_cache[Language.RU]
    
    @pytest.mark.asyncio
    async def test_concurrent_translations(self):
        """Проверяем потокобезопасность переводов"""
        manager = get_translation_manager()
        manager._translations_cache = {
            Language.RU: {"test.key": "Тест"},
            Language.EN: {"test.key": "Test"}
        }
        
        # Симулируем конкурентные запросы переводов
        async def translate_task(language):
            for _ in range(10):
                result = manager.t("test.key", language)
                expected = "Тест" if language == Language.RU else "Test"
                assert result == expected
        
        # Запускаем множество задач параллельно
        tasks = []
        for _ in range(5):
            tasks.append(translate_task(Language.RU))
            tasks.append(translate_task(Language.EN))
        
        # Все задачи должны выполниться успешно
        await asyncio.gather(*tasks)


class TestI18nErrorRecovery:
    """Тесты восстановления после ошибок"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
    
    @pytest.mark.asyncio
    async def test_corrupted_translation_file_recovery(self):
        """Проверяем восстановление после поврежденного файла переводов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TranslationManager()
            manager.config.translations_directory = str(Path(temp_dir) / "i18n")
            manager.translations_dir = Path(manager.config.translations_directory)
            
            await manager._ensure_directories()
            
            # Создаем поврежденный JSON файл
            corrupted_file = manager.translations_dir / "translations" / "ru.json"
            with open(corrupted_file, 'w') as f:
                f.write("{ invalid json content }")
            
            # Загрузка должна пройти без исключений
            await manager._load_translations()
            
            # Кеш для поврежденного языка должен быть пустым
            assert manager._translations_cache[Language.RU] == {}
    
    def test_translation_fallback_chain(self):
        """Проверяем цепочку fallback для переводов"""
        manager = get_translation_manager()
        
        # Настраиваем частичные переводы
        manager._translations_cache = {
            Language.RU: {
                "common.save": "Сохранить",
                "dashboard.title": "Панель управления"
            },
            Language.EN: {
                "common.save": "Save"
                # dashboard.title отсутствует
            },
            Language.ES: {
                # Полностью пустой
            }
        }
        
        # Тесты fallback
        # 1. EN -> RU fallback
        result = manager.t("dashboard.title", Language.EN)
        assert result == "Панель управления"
        
        # 2. ES -> RU fallback  
        result = manager.t("common.save", Language.ES)
        assert result == "Сохранить"
        
        # 3. Отсутствующий ключ -> возврат ключа
        result = manager.t("nonexistent.key", Language.RU)
        assert result == "nonexistent.key"
    
    def test_invalid_translation_params_handling(self):
        """Проверяем обработку некорректных параметров перевода"""
        manager = get_translation_manager()
        manager._translations_cache = {
            Language.RU: {
                "message.with.params": "Привет, {name}! Сегодня {date}.",
                "message.simple": "Простое сообщение"
            }
        }
        
        # 1. Недостающие параметры - должна быть ошибка или неподставленный шаблон
        result = manager.t("message.with.params", Language.RU, name="Иван")
        # Поскольку {date} отсутствует, format выбросит KeyError и в catch блоке вернется оригинальная строка
        assert result == "Привет, {name}! Сегодня {date}."
        
        # 2. Лишние параметры (не должны влиять)
        result = manager.t("message.simple", Language.RU, extra_param="unused")
        assert result == "Простое сообщение"
        
        # 3. Некорректные типы параметров
        result = manager.t("message.with.params", Language.RU, name=123, date=None)
        assert "123" in result


class TestI18nSystemIntegration:
    """Тесты системной интеграции с другими компонентами"""
    
    def test_integration_with_existing_field_system(self):
        """Проверяем интеграцию с существующей системой полей"""
        from pydantic import BaseModel
        from app.frontend.field_extensions import Field
        
        class IntegratedModel(BaseModel):
            # Поле с существующими frontend параметрами + i18n
            name: str = Field(
                title="Имя пользователя",
                readonly=True,
                hidden=False,
                css_class="user-name",
                i18n_title="models.user.name.title"
            )
            
            # Поле только с i18n параметрами
            description: str = Field(
                title="Описание", 
                i18n_title="models.user.description.title"
            )
            
            # Поле без i18n (должна сработать автогенерация)
            email: str = Field(
                title="Email адрес",
                placeholder="user@example.com"
            )
        
        # Проверяем JSON схему
        schema = IntegratedModel.model_json_schema()
        
        # Поле name
        name_field = schema["properties"]["name"]
        assert name_field["readonly"] is True
        assert name_field["css_class"] == "user-name"
        assert name_field["i18n_title"] == "models.user.name.title"
        
        # Поле description
        desc_field = schema["properties"]["description"]
        assert desc_field["i18n_title"] == "models.user.description.title"
        
        # Поле email (автогенерация)
        email_field = schema["properties"]["email"]
        assert email_field["i18n_title"] == "field.title.email_адрес"
        assert "placeholder" in email_field
    
    @patch('app.core.translation_manager.get_context')
    def test_template_and_api_consistency(self, mock_get_context):
        """Проверяем консистентность между template функциями и API"""
        # Подготавливаем контекст
        mock_user = User(
            user_id="consistency_user", 
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        test_context = Context(
            user=mock_user,
            platform="api",
            active_company=None,
            user_companies=[],
            language=Language.EN
        )
        mock_get_context.return_value = test_context
        
        # Подготавливаем менеджер
        manager = get_translation_manager()
        manager._translations_cache = {
            Language.EN: {
                "consistency.test": "Consistency Test",
                "param.message": "Hello, {name}!"
            }
        }
        
        # 1. Тест через глобальную функцию t()
        result1 = t("consistency.test")
        assert result1 == "Consistency Test"
        
        # 2. Тест через менеджер напрямую
        result2 = manager.t("consistency.test", Language.EN)
        assert result2 == "Consistency Test"
        
        # Результаты должны быть одинаковыми
        assert result1 == result2
        
        # 3. Тест с параметрами
        result3 = t("param.message", name="World")
        result4 = manager.t("param.message", Language.EN, name="World")
        
        assert result3 == result4 == "Hello, World!"
