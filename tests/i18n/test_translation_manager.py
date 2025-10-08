"""
Тесты для TranslationManager
"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from app.core.translation_manager import TranslationManager, get_translation_manager, t
from app.models.i18n_models import Language, TranslationKey, I18nConfig


class TestTranslationManagerSingleton:
    """Тесты паттерна Singleton для TranslationManager"""
    
    def test_singleton_pattern(self):
        """Проверяем что TranslationManager работает как singleton"""
        manager1 = TranslationManager()
        manager2 = TranslationManager() 
        
        assert manager1 is manager2
    
    def test_get_translation_manager(self):
        """Проверяем глобальную функцию получения менеджера"""
        manager1 = get_translation_manager()
        manager2 = get_translation_manager()
        
        assert manager1 is manager2
        assert isinstance(manager1, TranslationManager)


class TestTranslationManagerInit:
    """Тесты инициализации TranslationManager"""
    
    def setup_method(self):
        """Сброс singleton перед каждым тестом"""
        TranslationManager._instance = None
    
    def test_init_default_config(self):
        """Проверяем инициализацию с конфигурацией по умолчанию"""
        manager = TranslationManager()
        
        assert isinstance(manager.config, I18nConfig)
        assert manager.config.default_language == Language.RU
        assert manager.config.fallback_language == Language.RU
        assert manager.config.auto_generate_on_startup is True
    
    def test_init_directories_creation(self):
        """Проверяем создание директорий при инициализации"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Создаем новый менеджер с кастомной директорией
            manager = TranslationManager()
            manager.config.translations_directory = str(temp_path / "custom_i18n")
            manager.translations_dir = Path(manager.config.translations_directory)
            
            # Запускаем метод создания директорий
            asyncio.run(manager._ensure_directories())
            
            # Проверяем что директории созданы
            assert (temp_path / "custom_i18n" / "translations").exists()
            assert (temp_path / "custom_i18n" / "keys").exists()
            assert (temp_path / "custom_i18n" / "generated").exists()


class TestTranslationManagerBasicFunctionality:
    """Тесты базового функционала TranslationManager"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
        self.manager = TranslationManager()
        
        # Подготавливаем тестовые данные переводов
        self.test_translations = {
            Language.RU: {
                "common.save": "Сохранить",
                "common.cancel": "Отмена",
                "dashboard.title": "Панель управления",
                "validation.required": "Поле обязательно для заполнения"
            },
            Language.EN: {
                "common.save": "Save", 
                "common.cancel": "Cancel",
                "dashboard.title": "Dashboard",
                "validation.required": "Field is required"
            },
            Language.ES: {
                "common.save": "Guardar",
                "common.cancel": "Cancelar",
                "dashboard.title": "[TODO: dashboard.title]",
                "validation.required": "[TODO: validation.required]"
            }
        }
        
        # Загружаем тестовые переводы в менеджер
        self.manager._translations_cache = self.test_translations
    
    def test_t_function_existing_key(self):
        """Проверяем функцию перевода для существующего ключа"""
        # Русский язык
        result = self.manager.t("common.save", Language.RU)
        assert result == "Сохранить"
        
        # Английский язык
        result = self.manager.t("dashboard.title", Language.EN)
        assert result == "Dashboard"
    
    def test_t_function_missing_key(self):
        """Проверяем функцию перевода для отсутствующего ключа"""
        result = self.manager.t("nonexistent.key", Language.RU)
        assert result == "nonexistent.key"
    
    def test_t_function_fallback_language(self):
        """Проверяем fallback на основной язык"""
        # Добавляем ключ который есть только в RU
        self.manager._translations_cache[Language.RU]["test.fallback"] = "Только на русском"
        
        # Ключ отсутствует в ES, должен быть fallback на RU
        result = self.manager.t("test.fallback", Language.ES)
        assert result == "Только на русском"  # Fallback на RU
    
    def test_t_function_with_params(self):
        """Проверяем функцию перевода с параметрами"""
        # Добавляем перевод с параметрами
        self.manager._translations_cache[Language.RU]["welcome.message"] = "Добро пожаловать, {user_name}!"
        
        result = self.manager.t("welcome.message", Language.RU, user_name="Иван")
        assert result == "Добро пожаловать, Иван!"
    
    def test_t_function_invalid_params(self):
        """Проверяем обработку некорректных параметров"""
        # Добавляем перевод с параметрами
        self.manager._translations_cache[Language.RU]["welcome.message"] = "Добро пожаловать, {user_name}!"
        
        # Вызываем без необходимого параметра - должен остаться шаблон
        result = self.manager.t("welcome.message", Language.RU, wrong_param="Иван")
        assert "{user_name}" in result
    
    def test_get_translations(self):
        """Проверяем получение всех переводов для языка"""
        translations = self.manager.get_translations(Language.EN)
        
        assert isinstance(translations, dict)
        assert translations["common.save"] == "Save"
        assert translations["dashboard.title"] == "Dashboard"
        assert len(translations) == 4
    
    def test_get_translations_empty_language(self):
        """Проверяем получение переводов для неподдерживаемого языка"""
        # Очищаем кеш для одного языка
        del self.manager._translations_cache[Language.ES]
        
        translations = self.manager.get_translations(Language.ES)
        assert translations == {}
    
    def test_get_stats(self):
        """Проверяем получение статистики переводов"""
        stats = self.manager.get_stats()
        
        assert stats.total_languages == 3
        assert stats.total_keys == 4  # По количеству ключей в RU
        
        # Проверяем статистику по языкам
        ru_stats = stats.languages_stats[Language.RU]
        assert ru_stats.total_keys == 4
        assert ru_stats.translated_keys == 4
        assert ru_stats.completeness == 100.0
        
        es_stats = stats.languages_stats[Language.ES]
        assert es_stats.total_keys == 4
        assert es_stats.translated_keys == 2  # Только 2 без [TODO:]
        assert es_stats.completeness == 50.0


class TestTranslationManagerFileOperations:
    """Тесты файловых операций TranslationManager"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
        self.manager = TranslationManager()
    
    @pytest.mark.asyncio
    async def test_extract_nested_translations(self):
        """Проверяем извлечение переводов из вложенной структуры"""
        nested_data = {
            "meta": {
                "version": "1.0.0",
                "language": "ru"
            },
            "common": {
                "save": "Сохранить",
                "cancel": "Отмена"
            },
            "dashboard": {
                "title": "Панель управления",
                "navigation": {
                    "home": "Главная",
                    "settings": "Настройки"
                }
            }
        }
        
        result = {}
        self.manager._extract_nested_translations(nested_data, result)
        
        assert result["meta.version"] == "1.0.0"
        assert result["meta.language"] == "ru"
        assert result["common.save"] == "Сохранить"
        assert result["common.cancel"] == "Отмена"
        assert result["dashboard.title"] == "Панель управления"
        assert result["dashboard.navigation.home"] == "Главная"
        assert result["dashboard.navigation.settings"] == "Настройки"
        assert len(result) == 7  # Все ключи включая meta
    
    def test_set_nested_key(self):
        """Проверяем установку вложенного ключа"""
        data = {}
        
        self.manager._set_nested_key(data, "common.save", "Сохранить")
        self.manager._set_nested_key(data, "dashboard.navigation.home", "Главная")
        
        assert data["common"]["save"] == "Сохранить"
        assert data["dashboard"]["navigation"]["home"] == "Главная"
    
    def test_key_exists_in_data(self):
        """Проверяем проверку существования ключа в данных"""
        data = {
            "common": {
                "save": "Сохранить"
            },
            "dashboard": {
                "navigation": {
                    "home": "Главная"
                }
            }
        }
        
        assert self.manager._key_exists_in_data("common.save", data) is True
        assert self.manager._key_exists_in_data("dashboard.navigation.home", data) is True
        assert self.manager._key_exists_in_data("nonexistent.key", data) is False


class TestTranslationManagerCodeScanning:
    """Тесты сканирования кода для извлечения ключей переводов"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
        self.manager = TranslationManager()
    
    def test_is_pydantic_model(self):
        """Проверяем определение Pydantic моделей"""
        import ast
        
        # Создаем AST для класса-наследника BaseModel
        code = """
class User(BaseModel):
    name: str = Field(title="Имя пользователя")
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        
        assert self.manager._is_pydantic_model(class_node) is True
        
        # Проверяем обычный класс
        code2 = """
class RegularClass:
    pass
"""
        tree2 = ast.parse(code2)
        class_node2 = tree2.body[0]
        
        assert self.manager._is_pydantic_model(class_node2) is False
    
    def test_extract_field_params(self):
        """Проверяем извлечение параметров Field()"""
        import ast
        
        code = '''Field(title="Имя пользователя", description="Полное имя", placeholder="Введите имя")'''
        node = ast.parse(code, mode='eval').body
        
        params = self.manager._extract_field_params(node)
        
        assert params["title"] == "Имя пользователя"
        assert params["description"] == "Полное имя"
        assert params["placeholder"] == "Введите имя"
    
    @pytest.mark.asyncio
    async def test_scan_python_file(self):
        """Проверяем сканирование Python файла"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
from pydantic import BaseModel, Field

class User(BaseModel):
    name: str = Field(title="Имя пользователя", description="Полное имя пользователя")
    email: str = Field(title="Email", placeholder="user@example.com")
    
class NotAModel:
    pass
''')
            f.flush()
            
            await self.manager._scan_python_file(Path(f.name))
        
        # Проверяем что ключи добавились
        expected_keys = [
            "models.user.fields.name.title",
            "models.user.fields.name.description", 
            "models.user.fields.email.title",
            "models.user.fields.email.placeholder"
        ]
        
        for key in expected_keys:
            assert key in self.manager._discovered_keys
        
        # Проверяем содержимое
        name_title_key = self.manager._discovered_keys["models.user.fields.name.title"]
        assert name_title_key.default_value == "Имя пользователя"
        assert name_title_key.category == "models"
        
        # Удаляем временный файл
        Path(f.name).unlink()
    
    @pytest.mark.asyncio  
    async def test_scan_html_file(self):
        """Проверяем сканирование HTML файла"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write('''
<html>
    <body>
        <h1>{{ t('dashboard.title') }}</h1>
        <button>{{ t("common.save") }}</button>
        <p>{{ t('validation.required') }}</p>
    </body>
</html>
''')
            f.flush()
            
            await self.manager._scan_html_file(Path(f.name))
        
        # Проверяем что ключи добавились
        expected_keys = ["dashboard.title", "common.save", "validation.required"]
        
        for key in expected_keys:
            assert key in self.manager._discovered_keys
            assert self.manager._discovered_keys[key].category == "templates"
        
        # Удаляем временный файл
        Path(f.name).unlink()
    
    @pytest.mark.asyncio
    async def test_scan_js_file(self):
        """Проверяем сканирование JavaScript файла"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write('''
// Различные паттерны вызовов
app.i18n.t('dashboard.welcome');
this.languageManager.t("common.error");
i18n.t('validation.email_invalid');

function test() {
    return app.i18n.t('common.loading');
}
''')
            f.flush()
            
            await self.manager._scan_js_file(Path(f.name))
        
        # Проверяем что ключи добавились
        expected_keys = ["dashboard.welcome", "common.error", "validation.email_invalid", "common.loading"]
        
        for key in expected_keys:
            assert key in self.manager._discovered_keys
            assert self.manager._discovered_keys[key].category == "frontend"
        
        # Удаляем временный файл
        Path(f.name).unlink()


class TestGlobalTranslationFunction:
    """Тесты глобальной функции перевода"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
    
    def test_global_t_function(self):
        """Проверяем глобальную функцию t()"""
        # Подготавливаем менеджер с тестовыми данными
        manager = get_translation_manager()
        manager._translations_cache = {
            Language.RU: {"test.key": "Тестовое значение"}
        }
        
        result = t("test.key", Language.RU)
        assert result == "Тестовое значение"
    
    def test_global_t_function_with_params(self):
        """Проверяем глобальную функцию t() с параметрами"""
        manager = get_translation_manager()
        manager._translations_cache = {
            Language.RU: {"test.key": "Привет, {name}!"}
        }
        
        result = t("test.key", Language.RU, name="Мир")
        assert result == "Привет, Мир!"


class TestTranslationManagerContextIntegration:
    """Тесты интеграции с контекстом пользователя"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TranslationManager._instance = None
        self.manager = TranslationManager()
        self.manager._translations_cache = {
            Language.RU: {"test.key": "Русский текст"},
            Language.EN: {"test.key": "English text"}
        }
    
    @patch('app.core.translation_manager.get_context')
    def test_t_function_with_context_language(self, mock_get_context):
        """Проверяем автоматическое определение языка из контекста"""
        # Мокаем контекст с английским языком
        mock_context = Mock()
        mock_context.language = Language.EN
        mock_get_context.return_value = mock_context
        
        # Вызываем функцию без указания языка
        result = self.manager.t("test.key")
        assert result == "English text"
    
    @patch('app.core.translation_manager.get_context')
    def test_t_function_no_context(self, mock_get_context):
        """Проверяем работу без контекста (fallback на default)"""
        mock_get_context.return_value = None
        
        # Должен использовать язык по умолчанию (RU)
        result = self.manager.t("test.key")
        assert result == "Русский текст"
