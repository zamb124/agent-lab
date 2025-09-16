"""
Тесты для парсинга типов полей в фронтенд системе
"""
import pytest
from typing import List, Dict, Optional, Union
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel
from backend.app.frontend.field_extensions import get_template_name_from_type, Field


class SampleEnum(Enum):
    OPTION1 = "option1"
    OPTION2 = "option2"


class SampleModel(BaseModel):
    id: int
    name: str


class UserModel(BaseModel):
    user_id: str
    email: str


class PostModel(BaseModel):
    title: str
    content: str
    author: UserModel  # Модель как атрибут
    tags: List[str]


class TestFieldTypesParsing:
    """Тесты для парсинга типов полей"""

    def test_basic_types(self):
        """Тест базовых типов"""
        assert get_template_name_from_type(str) == "str"
        assert get_template_name_from_type(int) == "int"
        assert get_template_name_from_type(float) == "float"
        assert get_template_name_from_type(bool) == "bool"

    def test_optional_types(self):
        """Тест Optional типов"""
        assert get_template_name_from_type(Optional[str]) == "str"
        assert get_template_name_from_type(Optional[int]) == "int"
        assert get_template_name_from_type(Optional[List[str]]) == "list_str"

    def test_list_types(self):
        """Тест типов списков"""
        assert get_template_name_from_type(List[str]) == "list_str"
        assert get_template_name_from_type(List[int]) == "list_int"
        assert get_template_name_from_type(List[Dict[str, str]]) == "list_dict_str_str"

    def test_dict_types(self):
        """Тест типов словарей"""
        assert get_template_name_from_type(Dict[str, str]) == "dict_str_str"
        assert get_template_name_from_type(Dict[str, int]) == "dict_str_int"
        assert get_template_name_from_type(Dict[str, List[str]]) == "dict_str_list_str"

    def test_datetime_types(self):
        """Тест типов даты и времени"""
        assert get_template_name_from_type(datetime) == "datetime"
        assert get_template_name_from_type(date) == "date"

    def test_enum_types(self):
        """Тест типов перечислений"""
        assert get_template_name_from_type(SampleEnum) == "sampleenum"

    def test_model_types(self):
        """Тест типов моделей"""
        assert get_template_name_from_type(SampleModel) == "samplemodel"
        assert get_template_name_from_type(UserModel) == "usermodel"
        assert get_template_name_from_type(PostModel) == "postmodel"

    def test_model_as_field_type(self):
        """Тест модели как типа поля"""
        # Модель как обычное поле
        assert get_template_name_from_type(UserModel) == "usermodel"
        
        # Опциональная модель
        assert get_template_name_from_type(Optional[UserModel]) == "usermodel"
        
        # Список моделей
        assert get_template_name_from_type(List[UserModel]) == "list_usermodel"
        
        # Словарь с моделями
        assert get_template_name_from_type(Dict[str, UserModel]) == "dict_str_usermodel"

    def test_complex_nested_types(self):
        """Тест сложных вложенных типов"""
        complex_type = List[Dict[str, Optional[List[int]]]]
        result = get_template_name_from_type(complex_type)
        assert result == "list_dict_str_list_int"

    def test_union_types(self):
        """Тест Union типов (не Optional)"""
        union_type = Union[str, int]
        result = get_template_name_from_type(union_type)
        # Для Union берем строковое представление
        assert "union" in result.lower() or result in ["str", "int"]


class TestModelWithFields:
    """Тесты модели с расширенными полями"""

    def test_model_with_extended_fields(self):
        """Тест модели с расширенными полями"""
        
        class TestModelExtended(BaseModel):
            # Базовые типы
            name: str = Field(title="Имя", placeholder="Введите имя")
            age: int = Field(title="Возраст", description="Возраст в годах")
            is_active: bool = Field(title="Активен", readonly=True)
            
            # Опциональные типы
            email: Optional[str] = Field(title="Email")
            
            # Списки
            tags: List[str] = Field(title="Теги", description="Список тегов")
            scores: List[int] = Field(title="Баллы")
            
            # Словари
            metadata: Dict[str, str] = Field(title="Метаданные")
            
            # Сложные типы
            nested_data: Optional[List[Dict[str, int]]] = Field(
                title="Вложенные данные", 
                hidden=True
            )

        # Создаем экземпляр
        model = TestModelExtended(
            name="Тест",
            age=25,
            is_active=True,
            email="test@example.com",
            tags=["tag1", "tag2"],
            scores=[1, 2, 3],
            metadata={"key": "value"},
            nested_data=[{"a": 1, "b": 2}]
        )

        # Проверяем, что модель создается
        assert model.name == "Тест"
        assert model.age == 25
        
        # Проверяем, что у модели есть метод render
        assert hasattr(model, 'render')
        
        # Проверяем рендеринг
        html = model.render()
        assert isinstance(html, str)
        assert "Template: templates/fields/str.html" in html
        assert "Template: templates/fields/int.html" in html
        assert "Template: templates/fields/bool.html" in html
        assert "Template: templates/fields/email.html" in html  # render_type переопределен
        assert "Template: templates/fields/list_str.html" in html
        assert "Template: templates/fields/list_int.html" in html
        assert "Template: templates/fields/json.html" in html  # render_type переопределен
        # nested_data должен быть скрыт из-за hidden=True
        
    def test_field_config_extraction(self):
        """Тест извлечения конфигурации полей"""
        
        class ConfigTestModel(BaseModel):
            admin_field: str = Field(
                title="Админское поле",
                groups={
                    "admin": {"readonly": False, "hidden": False},
                    "user": {"readonly": True, "hidden": True}
                }
            )
            
        model = ConfigTestModel(admin_field="test")
        
        # Проверяем конфигурацию для админа
        admin_config = model.get_frontend_config("admin_field", "admin")
        assert admin_config['readonly'] == False
        assert admin_config['hidden'] == False
        
        # Проверяем конфигурацию для пользователя
        user_config = model.get_frontend_config("admin_field", "user")
        assert user_config['readonly'] == True
        assert user_config['hidden'] == True

    def test_field_info_access(self):
        """Тест доступа к информации о полях"""
        
        class InfoTestModel(BaseModel):
            test_field: str = Field(
                title="Тестовое поле",
                description="Описание тестового поля",
                placeholder="Введите значение"
            )
            
        model = InfoTestModel(test_field="test")
        
        # Проверяем получение информации о поле
        field_info = model.get_field_info("test_field")
        assert field_info is not None
        assert field_info.title == "Тестовое поле"
        assert field_info.description == "Описание тестового поля"
        
        # Проверяем получение всех конфигураций
        all_configs = model.get_all_frontend_configs()
        assert "test_field" in all_configs
        assert all_configs["test_field"]["placeholder"] == "Введите значение"

    def test_model_with_nested_models(self):
        """Тест модели с вложенными моделями"""
        
        class ComplexModel(BaseModel):
            # Простые поля
            title: str = Field(title="Заголовок")
            
            # Модель как поле
            author: UserModel = Field(title="Автор", description="Автор поста")
            
            # Опциональная модель
            editor: Optional[UserModel] = Field(
                default=None, 
                title="Редактор", 
                description="Редактор поста"
            )
            
            # Список моделей
            contributors: List[UserModel] = Field(
                default=[],
                title="Участники",
                description="Список участников"
            )
            
            # Словарь с моделями
            reviewers: Dict[str, UserModel] = Field(
                default={},
                title="Рецензенты",
                description="Словарь рецензентов"
            )
            
        # Создаем экземпляр
        user = UserModel(user_id="user1", email="user@example.com")
        model = ComplexModel(
            title="Тестовый пост",
            author=user,
            editor=user,
            contributors=[user],
            reviewers={"main": user}
        )
        
        # Проверяем рендеринг
        html = model.render()
        assert isinstance(html, str)
        
        # Проверяем что правильные шаблоны выбираются
        assert "Template: templates/fields/str.html" in html  # title
        assert "Template: templates/fields/usermodel.html" in html  # author
        assert "Template: templates/fields/usermodel.html" in html  # editor (Optional[UserModel] -> usermodel)
        assert "Template: templates/fields/list_usermodel.html" in html  # contributors
        assert "Template: templates/fields/dict_str_usermodel.html" in html  # reviewers
        
        # Проверяем что значения передаются
        assert "Field: title = Тестовый пост" in html
        assert "Field: author = " in html  # UserModel object
        
        print("HTML output:")
        print(html)


if __name__ == "__main__":
    pytest.main([__file__])
