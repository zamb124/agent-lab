"""
Тесты расширений полей Pydantic для интернационализации
"""

import pytest
from unittest.mock import Mock, patch
from pydantic import BaseModel

from app.frontend.field_extensions import Field, FrontendFieldInfo
from app.models.i18n_models import Language


class TestFrontendFieldInfoI18n:
    """Тесты i18n параметров в FrontendFieldInfo"""
    
    def test_field_with_explicit_i18n_keys(self):
        """Проверяем поле с явно заданными i18n ключами"""
        field_info = Field(
            title="Имя пользователя",
            description="Полное имя пользователя", 
            placeholder="Введите ваше имя",
            help_text="Имя будет отображаться в профиле",
            i18n_title="models.user.name.title",
            i18n_description="models.user.name.description",
            i18n_placeholder="models.user.name.placeholder",
            i18n_help_text="models.user.name.help_text"
        )
        
        # Проверяем что ключи сохранились
        json_extra = field_info.json_schema_extra
        assert json_extra["i18n_title"] == "models.user.name.title"
        assert json_extra["i18n_description"] == "models.user.name.description"  
        assert json_extra["i18n_placeholder"] == "models.user.name.placeholder"
        assert json_extra["i18n_help_text"] == "models.user.name.help_text"
        
        # Проверяем что оригинальные значения тоже сохранились
        assert json_extra["placeholder"] == "Введите ваше имя"
        assert json_extra["help_text"] == "Имя будет отображаться в профиле"
    
    def test_field_with_auto_generated_i18n_keys(self):
        """Проверяем автогенерацию i18n ключей"""
        field_info = Field(
            title="Имя пользователя",
            description="Полное имя пользователя",
            placeholder="Введите ваше имя",
            help_text="Имя будет отображаться в профиле"
        )
        
        json_extra = field_info.json_schema_extra
        
        # Проверяем автогенерированные ключи
        assert json_extra["i18n_title"] == "field.title.имя_пользователя"
        assert json_extra["i18n_description"].startswith("field.description.")
        assert json_extra["i18n_placeholder"].startswith("field.placeholder.")
        assert json_extra["i18n_help_text"].startswith("field.help_text.")
    
    def test_field_without_i18n_values(self):
        """Проверяем поле без значений для интернационализации"""
        field_info = Field(
            default="test_value"
            # Никаких title, description и т.д.
        )
        
        json_extra = field_info.json_schema_extra
        
        # i18n ключи должны быть None
        assert json_extra["i18n_title"] is None
        assert json_extra["i18n_description"] is None
        assert json_extra["i18n_placeholder"] is None
        assert json_extra["i18n_help_text"] is None
    
    def test_field_mixed_i18n_settings(self):
        """Проверяем поле с частично заданными i18n параметрами"""
        field_info = Field(
            title="Имя пользователя",
            description="Полное имя пользователя",
            i18n_title="custom.title.key",
            # i18n_description не задан - должен автогенерироваться
        )
        
        json_extra = field_info.json_schema_extra
        
        assert json_extra["i18n_title"] == "custom.title.key"
        assert json_extra["i18n_description"] == "field.description.полное_имя_пользователя"


class TestFieldI18nIntegrationWithModels:
    """Тесты интеграции i18n полей с Pydantic моделями"""
    
    def test_model_with_i18n_fields(self):
        """Проверяем модель с i18n полями"""
        class TestModel(BaseModel):
            name: str = Field(
                title="Имя пользователя",
                description="Полное имя пользователя",
                i18n_title="models.user.fields.name.title"
            )
            email: str = Field(
                title="Email",
                placeholder="user@example.com",
                i18n_placeholder="models.user.fields.email.placeholder"
            )
        
        # Проверяем схему модели
        schema = TestModel.model_json_schema()
        
        name_field = schema["properties"]["name"]
        email_field = schema["properties"]["email"]
        
        # Проверяем что i18n параметры попали в схему
        assert name_field.get("i18n_title") == "models.user.fields.name.title"
        assert email_field.get("i18n_placeholder") == "models.user.fields.email.placeholder"
    
    def test_field_info_extraction_from_model(self):
        """Проверяем извлечение информации о полях из модели"""
        class UserModel(BaseModel):
            username: str = Field(
                title="Имя пользователя",
                description="Уникальное имя пользователя",
                placeholder="Введите имя",
                help_text="Будет использовано для входа",
                i18n_title="models.user.username.title",
                i18n_help_text="models.user.username.help"
            )
        
        # Получаем JSON схему модели для извлечения метаданных полей
        schema = UserModel.model_json_schema()
        username_field = schema["properties"]["username"]
        
        # Проверяем что i18n данные попали в схему
        assert username_field["i18n_title"] == "models.user.username.title"
        assert username_field["i18n_help_text"] == "models.user.username.help" 
        assert username_field["title"] == "Имя пользователя"
        assert username_field.get("help_text") == "Будет использовано для входа"


class TestI18nFieldAutoGeneration:
    """Тесты автогенерации i18n ключей"""
    
    def test_i18n_key_normalization(self):
        """Проверяем нормализацию ключей при автогенерации"""
        test_cases = [
            ("Имя пользователя", "field.title.имя_пользователя"),
            ("Email адрес", "field.title.email_адрес"),
            ("Дата создания", "field.title.дата_создания"),
            ("User Name", "field.title.user_name"),
            ("Very Long Field Title That Should Be Normalized", "field.title.very_long_field_title_that_should_be_normal")  # Должно обрезаться
        ]
        
        for original_title, expected_key in test_cases:
            field_info = Field(title=original_title)
            json_extra = field_info.json_schema_extra
            
            # Проверяем что ключ сгенерировался правильно (с учетом возможного обрезания)
            generated_key = json_extra["i18n_title"]
            assert generated_key.startswith("field.title.")
            if len(expected_key) <= 50:
                assert generated_key == expected_key
    
    def test_i18n_key_special_characters(self):
        """Проверяем обработку специальных символов в автогенерации"""
        field_info = Field(
            title="Пользователь (активный)",
            description="Email адрес пользователя: test@example.com",
            placeholder="Введите email..."
        )
        
        json_extra = field_info.json_schema_extra
        
        # Проверяем что специальные символы заменились подчеркиваниями
        i18n_title = json_extra["i18n_title"]
        assert "(" not in i18n_title
        assert ")" not in i18n_title
        assert i18n_title == "field.title.пользователь_активный"
        
        i18n_description = json_extra["i18n_description"]  
        assert "@" not in i18n_description
        assert ":" not in i18n_description
        assert "example_com" in i18n_description  # Точка заменена на подчеркивание
        
        i18n_placeholder = json_extra["i18n_placeholder"]
        assert "." not in i18n_placeholder[-3:]  # Троеточие в конце убрано


class TestFieldI18nEdgeCases:
    """Тесты граничных случаев для i18n полей"""
    
    def test_field_with_none_values(self):
        """Проверяем поле с None значениями"""
        field_info = Field(
            title=None,
            description=None,
            placeholder=None,
            help_text=None
        )
        
        json_extra = field_info.json_schema_extra
        
        # Все i18n ключи должны быть None
        assert json_extra["i18n_title"] is None
        assert json_extra["i18n_description"] is None
        assert json_extra["i18n_placeholder"] is None
        assert json_extra["i18n_help_text"] is None
    
    def test_field_with_empty_strings(self):
        """Проверяем поле с пустыми строками"""
        field_info = Field(
            title="",
            description="",
            placeholder="",
            help_text=""
        )
        
        json_extra = field_info.json_schema_extra
        
        # i18n ключи не должны генерироваться для пустых строк
        assert json_extra["i18n_title"] is None
        assert json_extra["i18n_description"] is None
        assert json_extra["i18n_placeholder"] is None
        assert json_extra["i18n_help_text"] is None
    
    def test_field_backward_compatibility(self):
        """Проверяем обратную совместимость с существующими полями"""
        # Создаем поле в старом стиле (без i18n параметров)
        field_info = Field(
            title="Старое поле",
            description="Старое описание",
            readonly=True,
            hidden=False,
            css_class="old-field"
        )
        
        json_extra = field_info.json_schema_extra
        
        # Проверяем что старые параметры работают
        assert json_extra["readonly"] is True
        assert json_extra["hidden"] is False
        assert json_extra["css_class"] == "old-field"
        
        # И новые i18n параметры автогенерировались
        assert json_extra["i18n_title"] == "field.title.старое_поле"
        assert json_extra["i18n_description"].startswith("field.description.")
    
    def test_field_json_schema_extra_override(self):
        """Проверяем что json_schema_extra может перезаписать i18n ключи"""
        field_info = Field(
            title="Тест",
            json_schema_extra={"i18n_title": "custom.override.key"}
        )
        
        json_extra = field_info.json_schema_extra
        
        # Явно заданный json_schema_extra должен иметь приоритет
        assert json_extra["i18n_title"] == "custom.override.key"
