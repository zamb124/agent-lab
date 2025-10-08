"""
Расширения для Pydantic полей с дополнительной функциональностью для фронтенда
"""

from typing import Any, Dict, Optional, Union, List, get_origin, get_args
from pydantic import BaseModel
from pydantic.fields import FieldInfo
import pydantic
import re
import inspect
from app.frontend.core.template_loader import render_template, template_exists
from app.core.context import get_context


def get_template_name_from_type(annotation: Any, value: Any = None) -> str:
    """Получить имя шаблона по типу поля полностью динамически"""
    # Если есть реальное значение, используем его тип
    if value is not None:
        value_type = type(value)
        # Проверяем, является ли значение Enum
        if hasattr(value_type, "__bases__") and any(
            hasattr(base, "__name__") and base.__name__ == "Enum"
            for base in value_type.__bases__
        ):
            return "enum"
        # Проверяем, является ли значение BaseModel
        if isinstance(value, BaseModel):
            return "basemodel"
        return value_type.__name__.lower()

    # Убираем Optional - это единственное что нужно обработать специально
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            annotation = non_none_args[0]
            origin = get_origin(annotation)
        else:
            # Сложный Union - это ошибка дизайна модели!
            raise ValueError(
                f"Сложный Union тип не поддерживается: {annotation}. Исправьте модель!"
            )

    # Проверяем, является ли это Enum
    if hasattr(annotation, "__bases__") and any(
        hasattr(base, "__name__") and base.__name__ == "Enum"
        for base in annotation.__bases__
    ):
        return "enum"

    # Если есть origin (generic типы)
    if origin:
        origin_name = getattr(origin, "__name__", str(origin)).lower()
        args = get_args(annotation)
        if args:
            # Рекурсивно получаем имена для аргументов типа
            arg_names = [get_template_name_from_type(arg, value) for arg in args]
            return f"{origin_name}_{'_'.join(arg_names)}"
        else:
            return origin_name

    # Проверяем BaseModel
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return "basemodel"

    # Для обычных типов просто берем имя
    if hasattr(annotation, "__name__"):
        return annotation.__name__.lower()

    # Если ничего не подошло - это ошибка!
    raise ValueError(
        f"Неизвестный тип аннотации: {annotation}. Добавьте поддержку или исправьте модель!"
    )


class FrontendFieldInfo(FieldInfo):
    """Расширенная информация о поле с дополнительными атрибутами для фронтенда"""

    def __init__(
        self,
        default: Any = ...,
        *,
        # Стандартные Pydantic параметры
        default_factory: Optional[Any] = None,
        alias: Optional[str] = None,
        alias_priority: Optional[int] = None,
        validation_alias: Optional[Union[str, Any]] = None,
        serialization_alias: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        examples: Optional[list[Any]] = None,
        exclude: Optional[bool] = None,
        discriminator: Optional[Union[str, Any]] = None,
        json_schema_extra: Optional[Union[Dict[str, Any], Any]] = None,
        frozen: Optional[bool] = None,
        validate_default: Optional[bool] = None,
        repr: bool = True,
        init_var: Optional[bool] = None,
        kw_only: Optional[bool] = None,
        pattern: Optional[str] = None,
        strict: Optional[bool] = None,
        gt: Optional[float] = None,
        ge: Optional[float] = None,
        lt: Optional[float] = None,
        le: Optional[float] = None,
        multiple_of: Optional[float] = None,
        allow_inf_nan: Optional[bool] = None,
        max_digits: Optional[int] = None,
        decimal_places: Optional[int] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        coerce_numbers_to_str: Optional[bool] = None,
        # Расширенные параметры для фронтенда
        readonly: bool = False,
        hidden: bool = False,
        render: bool = False,
        groups: Optional[Dict[str, Dict[str, Any]]] = None,
        template: Optional[str] = None,
        placeholder: Optional[str] = None,
        help_text: Optional[str] = None,
        css_class: Optional[str] = None,
        widget_attrs: Optional[Dict[str, Any]] = None,
        editable_in_table: bool = True,
        sortable: bool = True,
        filterable: bool = True,
        searchable: bool = True,
        # Параметры интернационализации
        i18n_key: Optional[str] = None,
        i18n_title: Optional[str] = None,
        i18n_description: Optional[str] = None,
        i18n_placeholder: Optional[str] = None,
        i18n_help_text: Optional[str] = None,
        **kwargs,
    ):
        def normalize_key_part(text: str) -> str:
            """Нормализует текст для использования в качестве части ключа"""
            
            # Приводим к нижнему регистру и заменяем все не-буквы-цифры на подчеркивания
            normalized = re.sub(r'[^\w\s]', '_', text.lower())
            # Заменяем пробелы на подчеркивания
            normalized = re.sub(r'\s+', '_', normalized)
            # Убираем повторяющиеся подчеркивания
            normalized = re.sub(r'_+', '_', normalized)
            # Убираем подчеркивания в начале и конце
            normalized = normalized.strip('_')
            return normalized[:50]  # Ограничиваем длину

        # Автогенерация ключей переводов если не указаны явно
        if i18n_title is None and title:
            i18n_title = f"field.title.{normalize_key_part(title)}"
        if i18n_description is None and description:
            i18n_description = f"field.description.{normalize_key_part(description)}"
        if i18n_placeholder is None and placeholder:
            i18n_placeholder = f"field.placeholder.{normalize_key_part(placeholder)}"
        if i18n_help_text is None and help_text:
            i18n_help_text = f"field.help_text.{normalize_key_part(help_text)}"

        # Подготавливаем json_schema_extra с нашими расширениями
        frontend_extra = {
            "readonly": readonly,
            "hidden": hidden,
            "render": render,
            "groups": groups or {},
            "template": template,
            "placeholder": placeholder,
            "help_text": help_text,
            "css_class": css_class,
            "widget_attrs": widget_attrs or {},
            "editable_in_table": editable_in_table,
            "sortable": sortable,
            "filterable": filterable,
            "searchable": searchable,
            # Ключи интернационализации
            "i18n_key": i18n_key,
            "i18n_title": i18n_title,
            "i18n_description": i18n_description,
            "i18n_placeholder": i18n_placeholder,
            "i18n_help_text": i18n_help_text,
        }

        # Объединяем с существующим json_schema_extra
        # ВАЖНО: Сначала наши дефолты, потом существующий extra (чтобы не перезаписывать readonly от Field)
        if json_schema_extra:
            if callable(json_schema_extra):
                # Если это функция, создаем wrapper
                def combined_extra():
                    base_extra = json_schema_extra()
                    return {**frontend_extra, **base_extra}

                final_json_schema_extra = combined_extra
            elif isinstance(json_schema_extra, dict):
                # Сначала frontend_extra, потом json_schema_extra (приоритет у json_schema_extra)
                final_json_schema_extra = {**frontend_extra, **json_schema_extra}
            else:
                final_json_schema_extra = frontend_extra
        else:
            final_json_schema_extra = frontend_extra

        super().__init__(
            default=default,
            default_factory=default_factory,
            alias=alias,
            alias_priority=alias_priority,
            validation_alias=validation_alias,
            serialization_alias=serialization_alias,
            title=title,
            description=description,
            examples=examples,
            exclude=exclude,
            discriminator=discriminator,
            json_schema_extra=final_json_schema_extra,
            frozen=frozen,
            validate_default=validate_default,
            repr=repr,
            init_var=init_var,
            kw_only=kw_only,
            pattern=pattern,
            strict=strict,
            gt=gt,
            ge=ge,
            lt=lt,
            le=le,
            multiple_of=multiple_of,
            allow_inf_nan=allow_inf_nan,
            max_digits=max_digits,
            decimal_places=decimal_places,
            min_length=min_length,
            max_length=max_length,
            coerce_numbers_to_str=coerce_numbers_to_str,
            **kwargs,
        )

    def render(self, field_name: str, value: Any, annotation: Any, **kwargs) -> str:
        """Рендерить поле в HTML с учетом view_mode"""
        # Получаем конфигурацию фронтенда
        json_extra = self.json_schema_extra or {}
        if callable(json_extra):
            json_extra = json_extra()

        # Убираем Optional из аннотации для правильного определения типа
        clean_annotation = annotation
        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                clean_annotation = non_none_args[0]

        # 1. Проверяем переопределение шаблона в Field
        custom_template = json_extra.get("template")
        if custom_template:
            template_name = custom_template
        else:
            # 2. Автоматическое определение по типу
            type_name = get_template_name_from_type(clean_annotation, value)

            # Если это BaseModel и значение существует И является BaseModel
            if inspect.isclass(clean_annotation) and issubclass(clean_annotation, BaseModel):
                if value is not None and isinstance(value, BaseModel):
                    # Проверяем, есть ли render=True у поля
                    json_extra = self.json_schema_extra or {}
                    if callable(json_extra):
                        json_extra = json_extra()
                    
                    # Если render=True, то используем полный рендеринг
                    if json_extra.get("render", False):
                        field_view_mode = kwargs.get("view_mode", "form")
                        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'view_mode'}
                        return value.render(view_mode=field_view_mode, **clean_kwargs)
                    else:
                        # Если render=False (по умолчанию), используем компактный шаблон
                        template_name = "wrappers/compact.html"
                else:
                    # Для None BaseModel значений используем шаблон по типу значения
                    template_name = f"fields/{type_name}.html"
            else:
                template_name = f"fields/{type_name}.html"

        # Получаем view_mode из kwargs
        view_mode = kwargs.get("view_mode", "form")

        # Подготавливаем контекст для шаблона
        # Просто берем readonly из json_schema_extra (наш Field уже установил его)
        is_readonly = json_extra.get("readonly", False)
        
        context = {
            "field_name": field_name,
            "value": value,
            "title": self.title or field_name.replace("_", " ").title(),
            "description": self.description,
            "readonly": is_readonly,
            "hidden": json_extra.get("hidden", False),
            "placeholder": json_extra.get("placeholder"),
            "help_text": json_extra.get("help_text"),
            "css_class": json_extra.get("css_class", ""),
            "widget_attrs": json_extra.get("widget_attrs", {}),
            "view_mode": view_mode,  # Важно! Прокидываем view_mode в шаблон
            "field_config": json_extra,  # Добавляем field_config для совместимости с шаблонами
            **kwargs,
        }
        
        # Для BaseModel полей добавляем информацию о модели для compact.html
        if template_name == "wrappers/compact.html" and value and isinstance(value, BaseModel):
            model_type = value.get_model_prefix() if hasattr(value, 'get_model_prefix') else value.__class__.__name__.lower()
            
            # Получаем model_id, но проверяем, что это реальный ID, а не имя класса
            model_id = None
            if hasattr(value, 'get_model_id'):
                potential_id = value.get_model_id()
                # Если ID не равен имени класса в нижнем регистре, то это реальный ID
                if potential_id and potential_id != value.__class__.__name__.lower():
                    model_id = potential_id
            
            # Добавляем информацию о родительской модели из kwargs
            parent_model_type = kwargs.get("model_type")
            parent_model_id = kwargs.get("model_id")
            
            context.update({
                "model_type": model_type,
                "model_id": model_id,
                "parent_model_type": parent_model_type,
                "parent_model_id": parent_model_id
            })

        # Рендерим шаблон БЕЗ fallback
        return render_template(template_name, **context)


def Field(
    default: Any = ...,
    *,
    # Стандартные Pydantic параметры
    default_factory: Optional[Any] = None,
    alias: Optional[str] = None,
    alias_priority: Optional[int] = None,
    validation_alias: Optional[Union[str, Any]] = None,
    serialization_alias: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    examples: Optional[list[Any]] = None,
    exclude: Optional[bool] = None,
    discriminator: Optional[Union[str, Any]] = None,
    json_schema_extra: Optional[Union[Dict[str, Any], Any]] = None,
    frozen: Optional[bool] = None,
    validate_default: Optional[bool] = None,
    repr: bool = True,
    init_var: Optional[bool] = None,
    kw_only: Optional[bool] = None,
    pattern: Optional[str] = None,
    strict: Optional[bool] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    multiple_of: Optional[float] = None,
    allow_inf_nan: Optional[bool] = None,
    max_digits: Optional[int] = None,
    decimal_places: Optional[int] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    coerce_numbers_to_str: Optional[bool] = None,
    # Расширенные параметры для фронтенда
    readonly: bool = False,
    hidden: bool = False,
    render: bool = False,
    groups: Optional[Dict[str, Dict[str, Any]]] = None,
    template: Optional[str] = None,  # Переопределение шаблона поля
    placeholder: Optional[str] = None,
    help_text: Optional[str] = None,
    css_class: Optional[str] = None,
    widget_attrs: Optional[Dict[str, Any]] = None,
    editable_in_table: bool = True,
    sortable: bool = True,
    filterable: bool = True,
    searchable: bool = True,
    # Параметры интернационализации
    i18n_key: Optional[str] = None,
    i18n_title: Optional[str] = None,
    i18n_description: Optional[str] = None,
    i18n_placeholder: Optional[str] = None,
    i18n_help_text: Optional[str] = None,
) -> Any:
    """
    Расширенная версия Pydantic Field с дополнительными параметрами для фронтенда

    Дополнительные параметры:
    - readonly: Поле только для чтения
    - hidden: Скрытое поле
    - groups: Правила для групп пользователей {'admin': {'required': True}, 'user': {'hidden': False}}
    - placeholder: Placeholder для поля
    - help_text: Текст помощи
    - css_class: CSS класс для поля
    - widget_attrs: Дополнительные атрибуты для виджета
    - editable_in_table: Можно ли редактировать в таблице
    - sortable: Можно ли сортировать по полю
    - filterable: Можно ли фильтровать по полю
    - searchable: Участвует ли в поиске
    
    Параметры интернационализации:
    - i18n_key: Общий ключ перевода для поля
    - i18n_title: Ключ перевода для title (автогенерируется если не указан)
    - i18n_description: Ключ перевода для description (автогенерируется если не указан)
    - i18n_placeholder: Ключ перевода для placeholder (автогенерируется если не указан)  
    - i18n_help_text: Ключ перевода для help_text (автогенерируется если не указан)
    """
    return FrontendFieldInfo(
        default=default,
        default_factory=default_factory,
        alias=alias,
        alias_priority=alias_priority,
        validation_alias=validation_alias,
        serialization_alias=serialization_alias,
        title=title,
        description=description,
        examples=examples,
        exclude=exclude,
        discriminator=discriminator,
        json_schema_extra=json_schema_extra,
        frozen=frozen,
        validate_default=validate_default,
        repr=repr,
        init_var=init_var,
        kw_only=kw_only,
        pattern=pattern,
        strict=strict,
        gt=gt,
        ge=ge,
        lt=lt,
        le=le,
        multiple_of=multiple_of,
        allow_inf_nan=allow_inf_nan,
        max_digits=max_digits,
        decimal_places=decimal_places,
        min_length=min_length,
        max_length=max_length,
        coerce_numbers_to_str=coerce_numbers_to_str,
        readonly=readonly,
        hidden=hidden,
        render=render,
        groups=groups,
        template=template,
        placeholder=placeholder,
        help_text=help_text,
        css_class=css_class,
        widget_attrs=widget_attrs,
        editable_in_table=editable_in_table,
        sortable=sortable,
        filterable=filterable,
        searchable=searchable,
        i18n_key=i18n_key,
        i18n_title=i18n_title,
        i18n_description=i18n_description,
        i18n_placeholder=i18n_placeholder,
        i18n_help_text=i18n_help_text,
    )


# Патчим BaseModel для добавления методов работы с фронтендом
class FrontendMixin:
    """Миксин для добавления фронтенд функциональности к BaseModel"""

    def get_field_info(self, field_name: str) -> Optional[FrontendFieldInfo]:
        """Получить расширенную информацию о поле"""
        if (
            hasattr(self.__class__, "model_fields")
            and field_name in self.__class__.model_fields
        ):
            return self.__class__.model_fields[field_name]
        return None

    def get_frontend_config(
        self, field_name: str, user_group: Optional[str] = None
    ) -> Dict[str, Any]:
        """Получить конфигурацию поля для фронтенда с учетом группы пользователя"""
        field_info = self.get_field_info(field_name)
        if not field_info:
            return {}

        # Получаем базовую конфигурацию
        json_extra = field_info.json_schema_extra or {}
        if callable(json_extra):
            json_extra = json_extra()

        config = {
            "readonly": json_extra.get("readonly", False),
            "render": json_extra.get("render", False),
            "hidden": json_extra.get("hidden", False),
            "placeholder": json_extra.get("placeholder"),
            "help_text": json_extra.get("help_text"),
            "css_class": json_extra.get("css_class"),
            "widget_attrs": json_extra.get("widget_attrs", {}),
            "editable_in_table": json_extra.get("editable_in_table", True),
            "sortable": json_extra.get("sortable", True),
            "filterable": json_extra.get("filterable", True),
            "searchable": json_extra.get("searchable", True),
        }

        # Применяем правила для группы пользователя
        if user_group:
            groups = json_extra.get("groups", {})
            if user_group in groups:
                group_config = groups[user_group]
                config.update(group_config)

        return config

    def get_all_frontend_configs(
        self, user_group: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Получить конфигурации всех полей для фронтенда"""
        configs = {}
        if hasattr(self.__class__, "model_fields"):
            for field_name in self.__class__.model_fields:
                configs[field_name] = self.get_frontend_config(field_name, user_group)
        return configs

    def get_visible_data_for_group(
        self, user_groups: Union[str, List[str]]
    ) -> Dict[str, Any]:
        """Получить данные модели с учетом видимости полей для группы"""
        if isinstance(user_groups, str):
            user_groups = [user_groups]

        # Создаем копию данных модели
        model_data = self.model_dump()
        filtered_data = {}

        # Проходим по всем полям и применяем правила групп
        if hasattr(self.__class__, "model_fields"):
            for field_name, field_info in self.__class__.model_fields.items():
                # Проверяем видимость поля для группы
                if self.is_field_visible_for_group(field_name, user_groups):
                    filtered_data[field_name] = model_data.get(field_name)

        return filtered_data

    def get_field_for_group(
        self, field_name: str, user_groups: Union[str, List[str]]
    ) -> Dict[str, Any]:
        """Получить конфигурацию поля с примененными правилами групп"""
        if isinstance(user_groups, str):
            user_groups = [user_groups]

        # Получаем базовую конфигурацию поля
        base_config = self.get_frontend_config(field_name)

        field_info = self.get_field_info(field_name)
        if not field_info:
            return base_config

        json_extra = field_info.json_schema_extra or {}
        if callable(json_extra):
            json_extra = json_extra()

        groups_config = json_extra.get("groups", {})

        # Применяем правила для каждой группы пользователя
        final_config = base_config.copy()
        if user_groups:
            for user_group in user_groups:
                if user_group in groups_config:
                    group_rules = groups_config[user_group]
                    final_config.update(group_rules)

        # Добавляем enum опции если это enum поле
        if hasattr(field_info, "annotation"):
            annotation = field_info.annotation
            # Убираем Optional обертку
            origin = get_origin(annotation)
            if origin is Union:
                args = get_args(annotation)
                non_none_args = [arg for arg in args if arg is not type(None)]
                if len(non_none_args) == 1:
                    annotation = non_none_args[0]

            # Проверяем, является ли это Enum
            if hasattr(annotation, "__bases__") and any(
                hasattr(base, "__name__") and base.__name__ == "Enum"
                for base in annotation.__bases__
            ):
                # Получаем все опции enum'а
                final_config["enum_options"] = list(annotation)

        return final_config

    def is_field_visible_for_group(
        self, field_name: str, user_groups: Union[str, List[str]]
    ) -> bool:
        """Проверить, видимо ли поле для данной группы пользователей"""
        field_config = self.get_field_for_group(field_name, user_groups)
        return not field_config.get("hidden", False)

    def is_field_readonly_for_group(
        self, field_name: str, user_groups: Union[str, List[str]]
    ) -> bool:
        """Проверить, только ли для чтения поле для данной группы пользователей"""
        field_config = self.get_field_for_group(field_name, user_groups)
        return field_config.get("readonly", False)

    def is_field_required_for_group(
        self, field_name: str, user_groups: Union[str, List[str]]
    ) -> bool:
        """Проверить, обязательно ли поле для данной группы пользователей"""
        field_config = self.get_field_for_group(field_name, user_groups)
        return field_config.get("required", False)

    def get_visible_fields_for_group(
        self, user_groups: Union[str, List[str]]
    ) -> List[str]:
        """Получить список видимых полей для группы пользователей"""
        visible_fields = []
        if hasattr(self.__class__, "model_fields"):
            for field_name in self.__class__.model_fields:
                if self.is_field_visible_for_group(field_name, user_groups):
                    visible_fields.append(field_name)
        return visible_fields

    def _get_current_user_groups(self) -> List[str]:
        """Получить роли текущего пользователя в активной компании"""
        context = get_context()
        if not context or not context.user or not context.active_company:
            return ["user"]
        
        user = context.user
        company_id = context.active_company.company_id
        
        # Получаем роли пользователя в текущей компании
        if company_id in user.companies:
            return user.companies[company_id]
        
        return ["user"]

    def _get_model_class(self, model_type: str):
        """Получить класс модели по типу из registry"""
        from app.frontend.model_registry import ModelRegistry
        return ModelRegistry.get_model_class(model_type)

    def _render_fields(
        self, view_mode: str, user_groups: List[str], **kwargs
    ) -> List[str]:
        """Рендерить поля модели"""
        fields_html = []
        if hasattr(self.__class__, "model_fields"):
            for field_name, field_info in self.__class__.model_fields.items():
                # Проверяем видимость поля для групп пользователя
                if not self.is_field_visible_for_group(field_name, user_groups):
                    continue

                # Получаем значение поля
                value = getattr(self, field_name, None)

                # Получаем аннотацию типа
                annotation = field_info.annotation

                # Передаем view_mode в поле для правильного рендеринга
                field_kwargs = {
                    "user_groups": user_groups,
                    "field_config": self.get_field_for_group(field_name, user_groups),
                    "view_mode": view_mode,
                    "model_type": kwargs.get("model_type"),
                    "model_id": kwargs.get("model_id"),
                    **kwargs,
                }

                # Рендерим поле если у field_info есть метод render
                if hasattr(field_info, "render"):
                    field_html = field_info.render(
                        field_name, value, annotation, **field_kwargs
                    )
                    fields_html.append(field_html)
        return fields_html

    def render(self, view_mode: str = "form", **kwargs) -> str:
        """Простой рекурсивный рендеринг"""
        user_groups = self._get_current_user_groups()

        # 1. Определяем шаблон модели
        template_path = self._get_template_path(view_mode)

        # 2. Рендерим поля
        fields_html = []
        for field_name, field_info in self.__class__.model_fields.items():
            if not self.is_field_visible_for_group(field_name, user_groups):
                continue

            field_config = self.get_field_for_group(field_name, user_groups)

            # Если render=True - поле доступно в шаблоне, но не рендерится автоматически
            if field_config.get("render", False):
                continue

            # Рендерим обычное поле
            value = getattr(self, field_name, None)
            annotation = field_info.annotation

            if hasattr(field_info, "render"):
                field_html = field_info.render(
                    field_name,
                    value,
                    annotation,
                    view_mode=view_mode,
                    user_groups=user_groups,
                    **kwargs,
                )
                if field_html:
                    fields_html.append(field_html)
            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"⚠️ Поле {field_name} не имеет метода render! Тип: {type(field_info)}")

        # 3. Создаем контекст
        context = {
            "fields_html": "\n".join(fields_html),
            "view_mode": view_mode,
            **self.model_dump(),
            **kwargs,
        }

        # Добавляем поля с render=True как объекты
        for field_name, field_info in self.__class__.model_fields.items():
            field_config = self.get_field_for_group(field_name, user_groups)
            if field_config.get("render", False):
                context[field_name] = getattr(self, field_name)

        # Добавляем заголовки для таблиц
        if hasattr(self, "models") and self.models:
            headers = []
            first_model = self.models[0]
            model_class_name = first_model.__class__.__name__.lower().replace("config", "")
            
            for field_name, field_info in first_model.__class__.model_fields.items():
                # Пытаемся получить перевод для заголовка поля
                translation_key = f"models.{model_class_name}.fields.{field_name}.title"
                
                # Получаем контекст для доступа к функции перевода
                ctx = get_context()
                if ctx:
                    try:
                        from app.core.translation_manager import get_translation_manager
                        manager = get_translation_manager()
                        translated_title = manager.t(translation_key, ctx.language)
                        # Если перевод найден и не является ключом
                        if translated_title != translation_key and not translated_title.startswith("[TODO:"):
                            title = translated_title
                        else:
                            title = field_info.title or field_name.replace("_", " ").title()
                    except Exception as e:
                        title = field_info.title or field_name.replace("_", " ").title()
                else:
                    title = field_info.title or field_name.replace("_", " ").title()
                
                headers.append({"name": field_name, "title": title})
            context["headers"] = headers

        # 4. Рендерим шаблон или fallback
        if template_path:
            return render_template(template_path, **context)
        else:
            return "\n".join(fields_html)

    def _get_template_path(self, view_mode: str) -> str:
        """Определить путь к шаблону с поддержкой переопределения"""
        model_name = self.__class__.__name__

        # 1. Проверяем Config.templates для переопределения
        if hasattr(self.__class__, "Config") and hasattr(
            self.__class__.Config, "templates"
        ):
            custom_template = self.__class__.Config.templates.get(view_mode)
            if custom_template and template_exists(custom_template):
                return custom_template
            elif custom_template is None:
                # Явно указано None - не использовать шаблон
                return None

        # 2. Кастомный шаблон модели для view_mode
        auto_custom_template = f"models/{model_name}_{view_mode}.html"
        if template_exists(auto_custom_template):
            return auto_custom_template

        # 3. Общий шаблон модели
        model_template = f"models/{model_name}.html"
        if template_exists(model_template):
            return model_template

        # 4. Fallback wrapper
        fallback_template = f"wrappers/{view_mode}.html"
        if template_exists(fallback_template):
            return fallback_template
        return None

    def get_model_prefix(self) -> str:
        """Получить префикс модели для хранения в БД"""
        # Проверяем Config класс
        if hasattr(self.__class__, "Config") and hasattr(
            self.__class__.Config, "storage_prefix"
        ):
            return self.__class__.Config.storage_prefix

        # По умолчанию используем имя класса в нижнем регистре
        class_name = self.__class__.__name__.lower()
        if class_name.endswith("config"):
            class_name = class_name[:-6]
        return class_name

    def get_model_id(self) -> str:
        """Получить ID модели"""
        # Ищем поле с окончанием _id
        for field_name in self.__class__.model_fields:
            if field_name.endswith("_id"):
                return getattr(self, field_name)

        # Если не найдено, ищем поле id
        if hasattr(self, "id"):
            return self.id

        # Для моделей без ID возвращаем имя класса
        return self.__class__.__name__.lower()

    def get_storage_key(self) -> str:
        """Получить ключ для хранения в storage"""
        prefix = self.get_model_prefix()
        model_id = self.get_model_id()
        return f"{prefix}:{model_id}"


# Monkey patch BaseModel - добавляем методы напрямую к классу
for method_name in dir(FrontendMixin):
    if not method_name.startswith("__"):
        method = getattr(FrontendMixin, method_name)
        if callable(method):
            setattr(BaseModel, method_name, method)

# Monkey patch FieldInfo - добавляем метод render к обычным полям
def field_info_render(self, field_name: str, value: Any, annotation: Any, **kwargs) -> str:
    """Рендерить поле в HTML с учетом view_mode"""
    # Убираем конфликтующие параметры
    clean_kwargs = {k: v for k, v in kwargs.items() if k not in ['user_groups']}
    
    # Создаем временный FrontendFieldInfo для рендеринга
    frontend_field = FrontendFieldInfo(
        default=self.default,
        default_factory=self.default_factory,
        alias=self.alias,
        title=self.title,
        description=self.description,
        json_schema_extra=self.json_schema_extra,
        # Добавляем стандартные frontend параметры
        readonly=False,
        hidden=False,
        render=False,
    )
    return frontend_field.render(field_name, value, annotation, **clean_kwargs)

# Применяем monkey patch к FieldInfo
FieldInfo.render = field_info_render

# Глобальная функция для рендеринга в шаблонах
def render_model_safe(model, view_mode, **kwargs):
    """Безопасный рендеринг модели для шаблонов"""
    return model._render_internal(view_mode, **kwargs)
