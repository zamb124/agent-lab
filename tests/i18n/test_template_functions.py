"""
Тесты функций интернационализации для Jinja2 шаблонов
"""

from unittest.mock import Mock, patch
from jinja2 import Environment

from apps.frontend.core.template_loader import TemplateLoader
from core.models.i18n_models import Language
from core.models.context_models import Context
from core.models import User, AuthProvider, UserStatus


class TestTemplateI18nFunctions:
    """Тесты функций перевода в шаблонах"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        # Сбрасываем singleton TemplateLoader
        TemplateLoader._instance = None
    
    @patch('apps.frontend.core.template_loader.get_translation_manager')
    def test_t_function_in_template(self, mock_get_manager):
        """Проверяем функцию t() в шаблонах"""
        # Мокаем менеджер переводов
        mock_manager = Mock()
        mock_manager.t.return_value = "Dashboard"
        mock_get_manager.return_value = mock_manager
        
        # Создаем простой Jinja2 environment для тестов
        Environment()
        
        # Импортируем и добавляем функцию t
        loader = TemplateLoader()
        templates = loader.templates
        
        # Получаем функцию t из глобальных переменных
        t_function = templates.env.globals['t']
        
        # Вызываем функцию
        result = t_function("dashboard.title")
        
        assert result == "Dashboard"
        mock_manager.t.assert_called_once_with("dashboard.title")
    
    @patch('apps.frontend.core.template_loader.get_translation_manager')
    def test_t_function_with_params_in_template(self, mock_get_manager):
        """Проверяем функцию t() с параметрами в шаблонах"""
        mock_manager = Mock()
        mock_manager.t.return_value = "Welcome, John!"
        mock_get_manager.return_value = mock_manager
        
        loader = TemplateLoader()
        templates = loader.templates
        t_function = templates.env.globals['t']
        
        result = t_function("welcome.message", user_name="John")
        
        assert result == "Welcome, John!"
        mock_manager.t.assert_called_once_with("welcome.message", user_name="John")
    
    @patch('apps.frontend.core.template_loader.get_translation_manager')
    def test_t_function_exception_handling(self, mock_get_manager):
        """Проверяем обработку исключений в функции t()"""
        mock_get_manager.side_effect = Exception("Manager error")
        
        loader = TemplateLoader()
        templates = loader.templates
        t_function = templates.env.globals['t']
        
        # При исключении должен вернуться ключ
        result = t_function("test.key")
        assert result == "test.key"
    
    @patch('apps.frontend.core.template_loader.get_translation_manager')
    def test_t_field_function_with_i18n_key(self, mock_get_manager):
        """Проверяем функцию t_field() с i18n ключом"""
        mock_manager = Mock()
        mock_manager.t.return_value = "User Name"
        mock_get_manager.return_value = mock_manager
        
        loader = TemplateLoader()
        templates = loader.templates
        t_field_function = templates.env.globals['t_field']
        
        # Тестовые данные поля с i18n ключом
        field_info = {
            "title": "Имя пользователя",
            "i18n_title": "models.user.fields.name.title"
        }
        
        result = t_field_function(field_info, "title")
        
        assert result == "User Name"
        mock_manager.t.assert_called_once_with("models.user.fields.name.title")
    
    def test_t_field_function_fallback_to_original(self):
        """Проверяем fallback t_field() на оригинальное значение"""
        loader = TemplateLoader()
        templates = loader.templates
        t_field_function = templates.env.globals['t_field']
        
        # Поле без i18n ключа
        field_info = {
            "title": "Имя пользователя",
            "description": "Описание поля"
        }
        
        # Должно вернуться оригинальное значение
        result = t_field_function(field_info, "title")
        assert result == "Имя пользователя"
        
        result = t_field_function(field_info, "description")
        assert result == "Описание поля"
    
    @patch('apps.frontend.core.template_loader.get_translation_manager')
    def test_t_field_function_translation_not_found(self, mock_get_manager):
        """Проверяем t_field() когда перевод равен ключу (не найден)"""
        mock_manager = Mock()
        mock_manager.t.return_value = "models.user.fields.name.title"  # Возвращает ключ = не найден
        mock_get_manager.return_value = mock_manager
        
        loader = TemplateLoader()
        templates = loader.templates
        t_field_function = templates.env.globals['t_field']
        
        field_info = {
            "title": "Имя пользователя",
            "i18n_title": "models.user.fields.name.title"
        }
        
        # Если перевод не найден (равен ключу), должно вернуться оригинальное значение
        result = t_field_function(field_info, "title")
        assert result == "Имя пользователя"
    
    def test_t_field_function_missing_attribute(self):
        """Проверяем t_field() для отсутствующего атрибута"""
        loader = TemplateLoader()
        templates = loader.templates
        t_field_function = templates.env.globals['t_field']
        
        field_info = {
            "title": "Имя пользователя"
        }
        
        # Запрашиваем отсутствующий атрибут
        result = t_field_function(field_info, "nonexistent")
        assert result == ""
    
    def test_t_field_function_exception_handling(self):
        """Проверяем обработку исключений в t_field()"""
        loader = TemplateLoader()
        templates = loader.templates
        t_field_function = templates.env.globals['t_field']
        
        # Некорректные данные поля
        field_info = None
        
        result = t_field_function(field_info, "title")
        assert result == ""


class TestGetCurrentLanguageFunction:
    """Тесты функции get_current_language для шаблонов"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TemplateLoader._instance = None
    
    @patch('apps.frontend.core.template_loader.get_context')
    def test_get_current_language_from_context(self, mock_get_context):
        """Проверяем получение языка из контекста"""
        mock_user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        mock_context = Context(
            user=mock_user,
            platform="template",
            active_company=None,
            user_companies=[],
            language=Language.EN
        )
        mock_get_context.return_value = mock_context
        
        loader = TemplateLoader()
        templates = loader.templates
        get_current_language = templates.env.globals['get_current_language']
        
        result = get_current_language()
        assert result == "en"
    
    @patch('apps.frontend.core.template_loader.get_context')
    def test_get_current_language_no_context(self, mock_get_context):
        """Проверяем fallback при отсутствии контекста"""
        mock_get_context.return_value = None
        
        loader = TemplateLoader()
        templates = loader.templates
        get_current_language = templates.env.globals['get_current_language']
        
        result = get_current_language()
        assert result == "ru"  # Fallback
    
    @patch('apps.frontend.core.template_loader.get_context')
    def test_get_current_language_context_without_language(self, mock_get_context):
        """Проверяем fallback при контексте без атрибута language"""
        # Создаем контекст без language атрибута (старая версия)
        mock_context = Mock()
        mock_context.language = None  # Или отсутствует вообще
        mock_get_context.return_value = mock_context
        
        loader = TemplateLoader()
        templates = loader.templates
        get_current_language = templates.env.globals['get_current_language']
        
        result = get_current_language()
        assert result == "ru"  # Fallback
    
    @patch('apps.frontend.core.template_loader.get_context')
    def test_get_current_language_exception_handling(self, mock_get_context):
        """Проверяем обработку исключений в get_current_language()"""
        mock_get_context.side_effect = Exception("Context error")
        
        loader = TemplateLoader()
        templates = loader.templates  
        get_current_language = templates.env.globals['get_current_language']
        
        # При исключении должен вернуться fallback
        result = get_current_language()
        assert result == "ru"


class TestTemplateI18nIntegration:
    """Интеграционные тесты функций перевода в шаблонах"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        TemplateLoader._instance = None
    
    @patch('apps.frontend.core.template_loader.get_translation_manager')
    @patch('apps.frontend.core.template_loader.get_context')
    def test_full_template_rendering_with_i18n(self, mock_get_context, mock_get_manager):
        """Проверяем полный рендеринг шаблона с переводами"""
        # Подготавливаем контекст
        mock_user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123", 
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        mock_context = Context(
            user=mock_user,
            platform="template",
            active_company=None,
            user_companies=[],
            language=Language.EN
        )
        mock_get_context.return_value = mock_context
        
        # Подготавливаем менеджер переводов
        mock_manager = Mock()
        mock_manager.t.side_effect = lambda key, **kwargs: {
            "dashboard.title": "Dashboard",
            "welcome.message": f"Welcome, {kwargs.get('user_name', 'User')}!"
        }.get(key, key)
        mock_get_manager.return_value = mock_manager
        
        # Создаем и рендерим простой шаблон
        loader = TemplateLoader()
        templates = loader.templates
        
        template_str = """
        <h1>{{ t('dashboard.title') }}</h1>
        <p>{{ t('welcome.message', user_name='John') }}</p>
        <span>{{ get_current_language() }}</span>
        """
        
        template = templates.env.from_string(template_str)
        result = template.render()
        
        # Проверяем что переводы применились
        assert "Dashboard" in result
        assert "Welcome, John!" in result
        assert "en" in result
    
    def test_template_functions_availability(self):
        """Проверяем доступность всех i18n функций в шаблонах"""
        loader = TemplateLoader()
        templates = loader.templates
        
        # Проверяем что все функции добавлены в глобальные переменные
        assert 't' in templates.env.globals
        assert 't_field' in templates.env.globals
        assert 'get_current_language' in templates.env.globals
        
        # Проверяем что функции callable
        assert callable(templates.env.globals['t'])
        assert callable(templates.env.globals['t_field'])
        assert callable(templates.env.globals['get_current_language'])
