"""
Тесты для функциональности групп пользователей в фронтенд системе
"""
import pytest
from typing import List, Dict, Optional
from pydantic import BaseModel
from app.frontend.field_extensions import Field


class TestGroupsFunctionality:
    """Тесты для функциональности групп"""

    def test_basic_group_rules(self):
        """Тест базовых правил групп"""
        
        class GroupTestModel(BaseModel):
            # Поле видимое только админам
            admin_field: str = Field(
                title="Админское поле",
                groups={
                    "admin": {"hidden": False, "readonly": False},
                    "user": {"hidden": True, "readonly": True}
                }
            )
            
            # Поле обязательное для админов, опциональное для пользователей
            important_field: Optional[str] = Field(
                default=None,
                title="Важное поле",
                groups={
                    "admin": {"required": True, "readonly": False},
                    "user": {"required": False, "readonly": True},
                    "bot_editor": {"required": False, "readonly": False}
                }
            )
            
            # Обычное поле
            public_field: str = Field(title="Публичное поле")
            
        model = GroupTestModel(
            admin_field="admin_value",
            important_field="important_value",
            public_field="public_value"
        )
        
        # Тестируем для админа
        admin_config = model.get_field_for_group("admin_field", "admin")
        assert admin_config["hidden"] == False
        assert admin_config["readonly"] == False
        
        # Тестируем для пользователя
        user_config = model.get_field_for_group("admin_field", "user")
        assert user_config["hidden"] == True
        assert user_config["readonly"] == True
        
        # Тестируем обязательность для разных групп
        admin_important = model.get_field_for_group("important_field", "admin")
        assert admin_important["required"] == True
        assert admin_important["readonly"] == False
        
        user_important = model.get_field_for_group("important_field", "user")
        assert user_important["required"] == False
        assert user_important["readonly"] == True
        
        bot_editor_important = model.get_field_for_group("important_field", "bot_editor")
        assert bot_editor_important["required"] == False
        assert bot_editor_important["readonly"] == False

    def test_multiple_groups(self):
        """Тест применения правил для нескольких групп"""
        
        class MultiGroupModel(BaseModel):
            field1: str = Field(
                title="Поле 1",
                groups={
                    "admin": {"readonly": False},
                    "moderator": {"readonly": True},
                    "user": {"hidden": True}
                }
            )
            
        model = MultiGroupModel(field1="test_value")
        
        # Тестируем для пользователя с несколькими группами
        # Если пользователь и админ одновременно
        config = model.get_field_for_group("field1", ["user", "admin"])
        # Последняя группа в списке должна переопределить
        assert config["readonly"] == False  # от admin
        # Но hidden от user остается
        
        # Тестируем методы проверки
        assert model.is_field_visible_for_group("field1", "admin") == True
        assert model.is_field_visible_for_group("field1", "user") == False
        assert model.is_field_readonly_for_group("field1", "admin") == False
        assert model.is_field_readonly_for_group("field1", "moderator") == True

    def test_visible_fields_filtering(self):
        """Тест фильтрации видимых полей"""
        
        class FilterTestModel(BaseModel):
            public_field: str = Field(title="Публичное")
            admin_only: str = Field(
                title="Только админ",
                groups={"admin": {"hidden": False}, "user": {"hidden": True}}
            )
            user_visible: str = Field(
                title="Видимо пользователю",
                groups={"user": {"hidden": False}, "guest": {"hidden": True}}
            )
            
        model = FilterTestModel(
            public_field="public",
            admin_only="admin_secret",
            user_visible="user_data"
        )
        
        # Проверяем видимые поля для разных групп
        admin_fields = model.get_visible_fields_for_group("admin")
        assert "public_field" in admin_fields
        assert "admin_only" in admin_fields
        assert "user_visible" in admin_fields  # админ видит все
        
        user_fields = model.get_visible_fields_for_group("user")
        assert "public_field" in user_fields
        assert "admin_only" not in user_fields  # скрыто для user
        assert "user_visible" in user_fields
        
        guest_fields = model.get_visible_fields_for_group("guest")
        assert "public_field" in guest_fields  # нет правил = видимо
        assert "admin_only" in guest_fields    # нет правил для guest = видимо
        assert "user_visible" not in guest_fields  # скрыто для guest

    @pytest.mark.skip(reason="Тест устарел - изменилась сигнатура метода render")
    def test_render_with_groups(self):
        """Тест рендеринга с учетом групп"""
        
        class RenderTestModel(BaseModel):
            public_field: str = Field(title="Публичное поле")
            secret_field: str = Field(
                title="Секретное поле",
                groups={
                    "admin": {"hidden": False},
                    "user": {"hidden": True}
                }
            )
            readonly_field: str = Field(
                title="Поле только для чтения",
                groups={
                    "admin": {"readonly": False},
                    "user": {"readonly": True}
                }
            )
            
        model = RenderTestModel(
            public_field="public_value",
            secret_field="secret_value", 
            readonly_field="readonly_value"
        )
        
        # Рендеринг для админа
        admin_html = model.render(user_groups="admin")
        assert "Field: public_field = public_value" in admin_html
        assert "Field: secret_field = secret_value" in admin_html  # видимо для админа
        assert "Field: readonly_field = readonly_value" in admin_html
        
        # Рендеринг для пользователя
        user_html = model.render(user_groups="user")
        assert "Field: public_field = public_value" in user_html
        assert "Field: secret_field = secret_value" not in user_html  # скрыто для user
        assert "Field: readonly_field = readonly_value" in user_html
        
        # Рендеринг без групп (все поля видимы)
        all_html = model.render()
        assert "Field: public_field = public_value" in all_html
        assert "Field: secret_field = secret_value" in all_html
        assert "Field: readonly_field = readonly_value" in all_html

    def test_visible_data_for_group(self):
        """Тест получения видимых данных для группы"""
        
        class VisibleDataModel(BaseModel):
            visible_field: str = Field(title="Видимое поле")
            hidden_for_user: str = Field(
                title="Скрытое для пользователя",
                groups={"user": {"hidden": True}}
            )
            
        model = VisibleDataModel(
            visible_field="visible",
            hidden_for_user="hidden_value"
        )
        
        # Получаем видимые данные для пользователя
        user_data = model.get_visible_data_for_group("user")
        assert "visible_field" in user_data
        assert "hidden_for_user" not in user_data  # должно быть скрыто
        
        # Получаем видимые данные для админа (нет ограничений)
        admin_data = model.get_visible_data_for_group("admin")
        assert "visible_field" in admin_data
        assert "hidden_for_user" in admin_data  # должно быть видимо

    def test_complex_group_scenarios(self):
        """Тест сложных сценариев с группами"""
        
        class ComplexGroupModel(BaseModel):
            # Поле с разными правилами для разных групп
            multi_rule_field: str = Field(
                title="Поле с множественными правилами",
                groups={
                    "admin": {"readonly": False, "required": True, "hidden": False},
                    "bot_editor": {"readonly": False, "required": False, "hidden": False},
                    "user": {"readonly": True, "required": False, "hidden": False},
                    "guest": {"readonly": True, "required": False, "hidden": True}
                }
            )
            
            # Поле только для определенных групп
            special_field: Optional[str] = Field(
                default=None,
                title="Специальное поле",
                groups={
                    "admin": {"hidden": False, "readonly": False},
                    "bot_editor": {"hidden": False, "readonly": False}
                    # Для остальных групп правил нет = используются базовые настройки
                }
            )
            
        model = ComplexGroupModel(
            multi_rule_field="test_value",
            special_field="special_value"
        )
        
        # Проверяем для разных групп
        groups_to_test = ["admin", "bot_editor", "user", "guest"]
        
        for group in groups_to_test:
            print(f"\nТестируем группу: {group}")
            
            # Проверяем видимость
            visible = model.is_field_visible_for_group("multi_rule_field", group)
            print(f"  multi_rule_field видимо: {visible}")
            
            # Проверяем readonly
            readonly = model.is_field_readonly_for_group("multi_rule_field", group)
            print(f"  multi_rule_field readonly: {readonly}")
            
            # Проверяем required
            required = model.is_field_required_for_group("multi_rule_field", group)
            print(f"  multi_rule_field required: {required}")
            
            # Проверяем видимые поля
            visible_fields = model.get_visible_fields_for_group(group)
            print(f"  Видимые поля: {visible_fields}")
        
        # Конкретные проверки
        assert model.is_field_visible_for_group("multi_rule_field", "admin") == True
        assert model.is_field_visible_for_group("multi_rule_field", "guest") == False
        assert model.is_field_readonly_for_group("multi_rule_field", "admin") == False
        assert model.is_field_readonly_for_group("multi_rule_field", "user") == True
        assert model.is_field_required_for_group("multi_rule_field", "admin") == True
        assert model.is_field_required_for_group("multi_rule_field", "bot_editor") == False


if __name__ == "__main__":
    pytest.main([__file__])
