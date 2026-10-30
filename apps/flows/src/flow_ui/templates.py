"""Галерея документов интерфейса: единственная копия шаблонов, включая чат по умолчанию.

Шаблон — готовый :class:`FlowUIDocument` с текстами на языке запроса. Редактор
получает галерею через ``GET /flows/api/v1/flow-ui/templates``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from core.flow_ui.document import FlowUIDocument
from core.models.base import StrictBaseModel
from core.models.i18n_models import Language
from core.types import JsonObject

FlowUITemplateCategory = Literal["conversation", "forms", "dashboards", "content", "utility"]

DEFAULT_CHAT_TEMPLATE_ID = "chat"


class FlowUITemplate(StrictBaseModel):
    template_id: str
    category: FlowUITemplateCategory
    icon: str
    title: str
    description: str
    document: FlowUIDocument


class FlowUITemplatesPayload(StrictBaseModel):
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


def _copy(locale: Language, ru: str, en: str) -> str:
    return ru if locale is Language.RU else en


def _document(blocks: list[JsonObject], *, title: str) -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {"start_page_id": "main", "pages": [{"page_id": "main", "title": title, "blocks": blocks}]}
    )


def default_chat_document() -> FlowUIDocument:
    return _document(
        [
            {"type": "agent_identity", "block_id": "agent-identity"},
            {"type": "conversation", "block_id": "conversation"},
        ],
        title="Conversation",
    )


def _chat(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {"type": "agent_identity", "block_id": "agent-identity"},
            {
                "type": "conversation",
                "block_id": "conversation",
                "settings": {
                    "greeting": _copy(
                        locale, "Здравствуйте! Чем помочь?", "Hello! How can I help?"
                    ),
                    "suggested_prompts": [
                        _copy(locale, "Что ты умеешь?", "What can you do?"),
                        _copy(locale, "Покажи пример", "Show me an example"),
                    ],
                },
            },
        ],
        title=_copy(locale, "Диалог", "Conversation"),
    )


def _assistant_context(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {"type": "agent_identity", "block_id": "agent-identity"},
            {
                "type": "section",
                "block_id": "context",
                "title": _copy(locale, "Контекст", "Context"),
                "blocks": [
                    {
                        "type": "text",
                        "block_id": "context-text",
                        "markdown": _copy(
                            locale,
                            "Задача: {?task_title|не выбрана}",
                            "Task: {?task_title|not selected}",
                        ),
                    },
                    {"type": "slot", "block_id": "context-slot"},
                ],
            },
            {"type": "conversation", "block_id": "conversation"},
        ],
        title=_copy(locale, "Ассистент", "Assistant"),
    )


def _lead_form(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Чем можем помочь?", "How can we help?"),
                "level": 1,
            },
            {
                "type": "text",
                "block_id": "subtitle",
                "markdown": _copy(
                    locale,
                    "Оставьте заявку — агент ответит прямо в этом интерфейсе.",
                    "Leave a request and the agent will reply in this interface.",
                ),
            },
            {
                "type": "text_input",
                "block_id": "name",
                "field": "name",
                "label": _copy(locale, "Имя", "Name"),
                "required": True,
            },
            {
                "type": "text_input",
                "block_id": "email",
                "field": "email",
                "label": "Email",
                "required": True,
                "pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                "error_message": _copy(locale, "Введите корректный email", "Enter a valid email"),
            },
            {
                "type": "text_input",
                "block_id": "message",
                "field": "message",
                "label": _copy(locale, "Сообщение", "Message"),
                "multiline": True,
            },
            {
                "type": "button",
                "block_id": "submit",
                "label": _copy(locale, "Отправить заявку", "Send request"),
                "action": {"name": "submit"},
            },
        ],
        title=_copy(locale, "Заявка", "Request"),
    )


def _login(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Вход", "Sign in"),
                "level": 1,
            },
            {
                "type": "text_input",
                "block_id": "email",
                "field": "email",
                "label": "Email",
                "required": True,
            },
            {
                "type": "text_input",
                "block_id": "password",
                "field": "password",
                "label": _copy(locale, "Пароль", "Password"),
                "required": True,
                "secret": True,
            },
            {
                "type": "button",
                "block_id": "submit",
                "label": _copy(locale, "Войти", "Sign in"),
                "action": {"name": "login"},
            },
        ],
        title=_copy(locale, "Вход", "Sign in"),
    )


def _contact(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "avatar",
                "block_id": "avatar",
                "name": "{?contact.name|Support}",
                "image_url": "{?contact.image_url}",
            },
            {"type": "heading", "block_id": "title", "text": "{?contact.name|Support}", "level": 2},
            {"type": "text", "block_id": "role", "markdown": "{?contact.role}"},
            {
                "type": "text_input",
                "block_id": "message",
                "field": "message",
                "label": _copy(locale, "Сообщение", "Message"),
                "multiline": True,
                "required": True,
            },
            {
                "type": "button",
                "block_id": "send",
                "label": _copy(locale, "Написать", "Send"),
                "action": {"name": "send_message"},
            },
        ],
        title=_copy(locale, "Контакт", "Contact"),
    )


def _validated_form(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Регистрация", "Registration"),
                "level": 1,
            },
            {
                "type": "columns",
                "block_id": "name-row",
                "columns": [
                    {
                        "width": 6,
                        "blocks": [
                            {
                                "type": "text_input",
                                "block_id": "first-name",
                                "field": "first_name",
                                "label": _copy(locale, "Имя", "First name"),
                                "required": True,
                            }
                        ],
                    },
                    {
                        "width": 6,
                        "blocks": [
                            {
                                "type": "text_input",
                                "block_id": "last-name",
                                "field": "last_name",
                                "label": _copy(locale, "Фамилия", "Last name"),
                                "required": True,
                            }
                        ],
                    },
                ],
            },
            {
                "type": "text_input",
                "block_id": "phone",
                "field": "phone",
                "label": _copy(locale, "Телефон", "Phone"),
                "pattern": r"^\+?[0-9 ()-]{7,20}$",
                "error_message": _copy(locale, "Введите номер телефона", "Enter a phone number"),
            },
            {
                "type": "select",
                "block_id": "plan",
                "field": "plan",
                "label": _copy(locale, "Тариф", "Plan"),
                "options": [
                    {"value": "free", "label": _copy(locale, "Бесплатный", "Free")},
                    {"value": "pro", "label": "Pro"},
                    {"value": "team", "label": _copy(locale, "Команда", "Team")},
                ],
                "default": "free",
            },
            {
                "type": "checkbox",
                "block_id": "consent",
                "field": "consent",
                "label": _copy(locale, "Согласен с условиями", "I agree to the terms"),
                "required": True,
            },
            {
                "type": "button",
                "block_id": "submit",
                "label": _copy(locale, "Зарегистрироваться", "Register"),
                "action": {"name": "register"},
            },
        ],
        title=_copy(locale, "Форма", "Form"),
    )


def _dashboard(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Обзор", "Overview"),
                "level": 1,
            },
            {
                "type": "columns",
                "block_id": "metrics",
                "columns": [
                    {
                        "width": 4,
                        "blocks": [
                            {
                                "type": "metric",
                                "block_id": "revenue",
                                "label": _copy(locale, "Выручка", "Revenue"),
                                "value": "{?metrics.revenue|0}",
                            }
                        ],
                    },
                    {
                        "width": 4,
                        "blocks": [
                            {
                                "type": "metric",
                                "block_id": "orders",
                                "label": _copy(locale, "Заказы", "Orders"),
                                "value": "{?metrics.orders|0}",
                            }
                        ],
                    },
                    {
                        "width": 4,
                        "blocks": [
                            {
                                "type": "metric",
                                "block_id": "customers",
                                "label": _copy(locale, "Клиенты", "Customers"),
                                "value": "{?metrics.customers|0}",
                            }
                        ],
                    },
                ],
            },
            {
                "type": "chart",
                "block_id": "chart",
                "kind": "line",
                "title": _copy(locale, "Динамика", "Trend"),
                "data": "metrics.series",
                "x": "date",
                "y": ["revenue"],
            },
            {
                "type": "data_table",
                "block_id": "table",
                "rows": "metrics.rows",
                "row_action": {"name": "open_row"},
            },
            {"type": "conversation", "block_id": "conversation"},
        ],
        title=_copy(locale, "Дашборд", "Dashboard"),
    )


def _stats_overview(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Статистика", "Statistics"),
                "level": 1,
            },
            {
                "type": "status",
                "block_id": "status",
                "label": "{?stats.status|ok}",
                "tone": "success",
            },
            {
                "type": "progress",
                "block_id": "progress",
                "label": _copy(locale, "Выполнено", "Completed"),
                "value": "{?stats.progress|0}",
            },
            {
                "type": "columns",
                "block_id": "cards",
                "columns": [
                    {
                        "width": 6,
                        "blocks": [
                            {
                                "type": "metric",
                                "block_id": "active",
                                "label": _copy(locale, "Активные", "Active"),
                                "value": "{?stats.active|0}",
                            }
                        ],
                    },
                    {
                        "width": 6,
                        "blocks": [
                            {
                                "type": "metric",
                                "block_id": "done",
                                "label": _copy(locale, "Завершённые", "Done"),
                                "value": "{?stats.done|0}",
                            }
                        ],
                    },
                ],
            },
            {
                "type": "button",
                "block_id": "refresh",
                "label": _copy(locale, "Обновить", "Refresh"),
                "action": {"name": "refresh"},
                "variant": "secondary",
            },
        ],
        title=_copy(locale, "Статистика", "Statistics"),
    )


def _status_tracker(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(
                    locale, "Статус заказа {?order.number}", "Order {?order.number} status"
                ),
                "level": 1,
            },
            {
                "type": "status",
                "block_id": "status",
                "label": "{?order.status|pending}",
                "tone": "info",
            },
            {"type": "progress", "block_id": "progress", "value": "{?order.progress|0}"},
            {
                "type": "activity",
                "block_id": "activity",
                "title": "{?order.stage|Processing}",
                "status": "running",
            },
            {
                "type": "alert",
                "block_id": "delivered",
                "message": _copy(locale, "Заказ доставлен", "Order delivered"),
                "tone": "success",
                "visible_when": {"path": "order.status", "equals": "delivered"},
            },
            {
                "type": "button",
                "block_id": "refresh",
                "label": _copy(locale, "Обновить", "Refresh"),
                "action": {"name": "refresh"},
                "variant": "secondary",
            },
        ],
        title=_copy(locale, "Статус", "Status"),
    )


def _task_list(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Задачи", "Tasks"),
                "level": 1,
            },
            {
                "type": "empty_state",
                "block_id": "empty",
                "message": _copy(locale, "Задач пока нет", "No tasks yet"),
                "visible_when": {"path": "tasks_empty"},
            },
            {
                "type": "data_table",
                "block_id": "tasks",
                "rows": "tasks",
                "columns": [
                    {"key": "title", "label": _copy(locale, "Название", "Title")},
                    {"key": "status", "label": _copy(locale, "Статус", "Status")},
                ],
                "row_action": {"name": "open_task"},
            },
            {
                "type": "text_input",
                "block_id": "new-task",
                "field": "task_title",
                "label": _copy(locale, "Новая задача", "New task"),
                "required": True,
            },
            {
                "type": "button",
                "block_id": "add",
                "label": _copy(locale, "Добавить", "Add"),
                "action": {"name": "add_task"},
            },
        ],
        title=_copy(locale, "Задачи", "Tasks"),
    )


def _product_detail(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "columns",
                "block_id": "layout",
                "columns": [
                    {
                        "width": 5,
                        "blocks": [
                            {
                                "type": "image",
                                "block_id": "photo",
                                "url": "{?product.image_url}",
                                "alt": "{?product.title}",
                            }
                        ],
                    },
                    {
                        "width": 7,
                        "blocks": [
                            {
                                "type": "heading",
                                "block_id": "title",
                                "text": "{?product.title|Product}",
                                "level": 1,
                            },
                            {
                                "type": "text",
                                "block_id": "description",
                                "markdown": "{?product.description}",
                            },
                            {
                                "type": "metric",
                                "block_id": "price",
                                "label": _copy(locale, "Цена", "Price"),
                                "value": "{?product.price|—}",
                            },
                            {
                                "type": "number_input",
                                "block_id": "quantity",
                                "field": "quantity",
                                "label": _copy(locale, "Количество", "Quantity"),
                                "default": 1,
                                "min": 1,
                            },
                            {
                                "type": "button",
                                "block_id": "buy",
                                "label": _copy(locale, "Купить", "Buy"),
                                "action": {"name": "buy"},
                            },
                        ],
                    },
                ],
            },
        ],
        title=_copy(locale, "Товар", "Product"),
    )


def _purchase_complete(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "alert",
                "block_id": "done",
                "title": _copy(locale, "Спасибо за покупку!", "Thank you for your purchase!"),
                "message": _copy(
                    locale, "Номер заказа: {?order.number}", "Order number: {?order.number}"
                ),
                "tone": "success",
            },
            {
                "type": "metric",
                "block_id": "total",
                "label": _copy(locale, "Итого", "Total"),
                "value": "{?order.total|0}",
            },
            {"type": "file_list", "block_id": "receipts", "files": "files"},
            {
                "type": "button",
                "block_id": "again",
                "label": _copy(locale, "Новый заказ", "New order"),
                "action": {"name": "new_order"},
                "variant": "secondary",
            },
        ],
        title=_copy(locale, "Готово", "Done"),
    )


def _user_profile(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "avatar",
                "block_id": "avatar",
                "name": "{?profile.name|User}",
                "image_url": "{?profile.image_url}",
            },
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Профиль", "Profile"),
                "level": 1,
            },
            {
                "type": "text_input",
                "block_id": "name",
                "field": "profile.name",
                "label": _copy(locale, "Имя", "Name"),
                "required": True,
            },
            {
                "type": "text_input",
                "block_id": "email",
                "field": "profile.email",
                "label": "Email",
                "required": True,
            },
            {
                "type": "switch",
                "block_id": "notifications",
                "field": "profile.notifications",
                "label": _copy(locale, "Уведомления", "Notifications"),
                "action": {"name": "toggle_notifications"},
            },
            {
                "type": "button",
                "block_id": "save",
                "label": _copy(locale, "Сохранить", "Save"),
                "action": {"name": "save_profile"},
            },
        ],
        title=_copy(locale, "Профиль", "Profile"),
    )


def _event_detail(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "image",
                "block_id": "cover",
                "url": "{?event.image_url}",
                "alt": "{?event.title}",
            },
            {"type": "heading", "block_id": "title", "text": "{?event.title|Event}", "level": 1},
            {"type": "badge", "block_id": "date", "label": "{?event.starts_at}", "tone": "info"},
            {"type": "text", "block_id": "description", "markdown": "{?event.description}"},
            {
                "type": "text_input",
                "block_id": "email",
                "field": "email",
                "label": "Email",
                "required": True,
            },
            {
                "type": "button",
                "block_id": "register",
                "label": _copy(locale, "Зарегистрироваться", "Register"),
                "action": {"name": "register"},
            },
        ],
        title=_copy(locale, "Событие", "Event"),
    )


def _notification_center(locale: Language) -> FlowUIDocument:
    return _document(
        [
            {
                "type": "heading",
                "block_id": "title",
                "text": _copy(locale, "Уведомления", "Notifications"),
                "level": 1,
            },
            {
                "type": "switch",
                "block_id": "email-switch",
                "field": "settings.email",
                "label": _copy(locale, "Почта", "Email"),
                "action": {"name": "update_settings"},
            },
            {
                "type": "switch",
                "block_id": "push-switch",
                "field": "settings.push",
                "label": "Push",
                "action": {"name": "update_settings"},
            },
            {"type": "divider", "block_id": "divider"},
            {
                "type": "data_table",
                "block_id": "list",
                "rows": "notifications",
                "row_action": {"name": "open_notification"},
            },
        ],
        title=_copy(locale, "Уведомления", "Notifications"),
    )


def _blank(locale: Language) -> FlowUIDocument:
    return _document([], title=_copy(locale, "Страница", "Page"))


def flow_ui_templates(locale: Language) -> list[FlowUITemplate]:
    return [
        FlowUITemplate(
            template_id=DEFAULT_CHAT_TEMPLATE_ID,
            category="conversation",
            icon="chat",
            title=_copy(locale, "Агентский чат", "Agent chat"),
            description=_copy(
                locale,
                "Лента диалога, приветствие, подсказки и композер с файлами и голосом.",
                "Conversation feed, greeting, prompts and a composer with files and voice.",
            ),
            document=_chat(locale),
        ),
        FlowUITemplate(
            template_id="assistant_context",
            category="conversation",
            icon="layers",
            title=_copy(locale, "Чат с контекстом", "Chat with context"),
            description=_copy(
                locale,
                "Диалог плюс блок контекста над лентой.",
                "Conversation plus a context block above the feed.",
            ),
            document=_assistant_context(locale),
        ),
        FlowUITemplate(
            template_id="lead_form",
            category="forms",
            icon="checklist",
            title=_copy(locale, "Заявка", "Request form"),
            description=_copy(
                locale,
                "Заголовок, описание и форма заявки: имя, email, сообщение.",
                "Headline, description and a request form: name, email, message.",
            ),
            document=_lead_form(locale),
        ),
        FlowUITemplate(
            template_id="login",
            category="forms",
            icon="lock",
            title=_copy(locale, "Вход", "Login form"),
            description=_copy(
                locale,
                "Экран входа: email, пароль и кнопка.",
                "Sign-in screen: email, password and a button.",
            ),
            document=_login(locale),
        ),
        FlowUITemplate(
            template_id="contact",
            category="forms",
            icon="users",
            title=_copy(locale, "Контакт", "Contact card"),
            description=_copy(
                locale,
                "Карточка контакта с аватаром и форма сообщения.",
                "Contact card with avatar and a message form.",
            ),
            document=_contact(locale),
        ),
        FlowUITemplate(
            template_id="validated_form",
            category="forms",
            icon="check-square",
            title=_copy(locale, "Форма с проверками", "Validated form"),
            description=_copy(
                locale,
                "Обязательные поля, шаблоны и колонки.",
                "Required fields, patterns and columns.",
            ),
            document=_validated_form(locale),
        ),
        FlowUITemplate(
            template_id="dashboard",
            category="dashboards",
            icon="apps",
            title=_copy(locale, "Дашборд", "Dashboard"),
            description=_copy(
                locale, "Метрики, график, таблица и чат.", "Metrics, chart, table and chat."
            ),
            document=_dashboard(locale),
        ),
        FlowUITemplate(
            template_id="stats_overview",
            category="dashboards",
            icon="chart",
            title=_copy(locale, "Статистика", "Stats overview"),
            description=_copy(
                locale,
                "Статус, прогресс и карточки показателей.",
                "Status, progress and metric cards.",
            ),
            document=_stats_overview(locale),
        ),
        FlowUITemplate(
            template_id="status_tracker",
            category="utility",
            icon="schedule",
            title=_copy(locale, "Трекер статуса", "Status tracker"),
            description=_copy(
                locale,
                "Статус, прогресс, активность и условный блок.",
                "Status, progress, activity and a conditional block.",
            ),
            document=_status_tracker(locale),
        ),
        FlowUITemplate(
            template_id="task_list",
            category="utility",
            icon="list-check",
            title=_copy(locale, "Список задач", "Task list"),
            description=_copy(
                locale,
                "Таблица задач с действием по строке и добавлением.",
                "Task table with row action and quick add.",
            ),
            document=_task_list(locale),
        ),
        FlowUITemplate(
            template_id="product_detail",
            category="content",
            icon="tag",
            title=_copy(locale, "Товар", "Product detail"),
            description=_copy(
                locale, "Фото, описание, цена и покупка.", "Photo, description, price and purchase."
            ),
            document=_product_detail(locale),
        ),
        FlowUITemplate(
            template_id="purchase_complete",
            category="content",
            icon="done-all",
            title=_copy(locale, "Покупка завершена", "Purchase complete"),
            description=_copy(
                locale, "Подтверждение, итог и файлы.", "Confirmation, total and files."
            ),
            document=_purchase_complete(locale),
        ),
        FlowUITemplate(
            template_id="user_profile",
            category="content",
            icon="user",
            title=_copy(locale, "Профиль", "User profile"),
            description=_copy(
                locale,
                "Аватар, поля профиля и переключатели.",
                "Avatar, profile fields and switches.",
            ),
            document=_user_profile(locale),
        ),
        FlowUITemplate(
            template_id="event_detail",
            category="content",
            icon="calendar",
            title=_copy(locale, "Событие", "Event detail"),
            description=_copy(
                locale, "Обложка, описание и регистрация.", "Cover, description and registration."
            ),
            document=_event_detail(locale),
        ),
        FlowUITemplate(
            template_id="notification_center",
            category="utility",
            icon="bell-ring",
            title=_copy(locale, "Центр уведомлений", "Notification center"),
            description=_copy(
                locale,
                "Переключатели каналов и список уведомлений.",
                "Channel switches and a notification list.",
            ),
            document=_notification_center(locale),
        ),
        FlowUITemplate(
            template_id="blank",
            category="utility",
            icon="square",
            title=_copy(locale, "Пустая страница", "Blank page"),
            description=_copy(locale, "Начните с чистого листа.", "Start from scratch."),
            document=_blank(locale),
        ),
    ]


__all__ = [
    "DEFAULT_CHAT_TEMPLATE_ID",
    "FlowUITemplate",
    "FlowUITemplateCategory",
    "FlowUITemplatesPayload",
    "default_chat_document",
    "flow_ui_templates",
]
