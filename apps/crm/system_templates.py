"""
Системные шаблоны CRM/Networkle.

Networkle — мета-сервис: пользователь собирает себе любой CRM-домен из
неймспейсов и типов сущностей. Этот модуль — единственный источник правды
системных шаблонов, которые платформа предоставляет «из коробки».

Источник правды: код этого модуля. Применяется через `CompanyInitService`
(старт сервиса + первый запрос компании в процессе) и
`NamespaceTemplateService.create_namespace_from_template`.

Канон системного шаблона
========================

Тип сущности (`SYSTEM_ENTITY_TYPE_TEMPLATES`, `COMMON_NAMESPACE_ANCHOR_TYPES`,
а также элементы `seed["types"]` в `NAMESPACE_TEMPLATE_SEEDS`):

- `name` — короткое отображаемое имя на русском.
- `description` — что это, чем отличается от похожих типов; ≥30 символов.
- `prompt` — для extractable=True: «Что извлекать → 2–3 примера → что НЕ
  извлекать»; ≥120 символов; используется AI в bundle `crm/analyze`.
- `required_fields` / `optional_fields` — каждое поле обязано иметь
  `type`, `label`, `description`. Для `enum`: `values` непустой и
  `description` содержит расшифровку каждого значения.
- Семантические флаги (`is_event`, `is_context_anchor`, `is_voice_target`,
  `extractable`, `check_duplicates`) — обоснованы политикой:
  заметки/встречи/звонки не якоря; person-сущности — voice_target;
  заметки и черновики — `check_duplicates=False`.
- `icon`, `color` — из палитры платформы.

Тип связи (`SYSTEM_RELATIONSHIP_TYPE_TEMPLATES`):

- `name`, `description`.
- `is_directed`, опционально `inverse_type_id`, `weight_default`.
- `prompt` для AI-используемых типов: «Когда использовать → примеры →
  когда НЕ использовать»; ≥150 символов.

Шаблон пространства (`NAMESPACE_TEMPLATE_SEEDS`):

- `template_id` (snake_case), `name`, `description`, `icon`.
- `types` — список спецификаций типов того же канона.
- `crm_settings` — `pipeline_stage_presets` для всех досок задач шаблона
  (включая `task` и `task:<subtype>`), `default_note_voice`,
  `show_note_voice_ui`. Сидируется в БД через
  `CompanyInitService._init_namespace_templates` (reseed на каждом старте
  для is_system).

Reseed обновляет только системные строки в БД (типы пространства
`default` и `is_system=True` шаблоны). Уже созданные пользователями
пространства (копии из шаблона) **не обновляются** автоматически — их
правит пользователь руками в UI.
"""

from typing import Any

from apps.crm.constants_graph import (
    CALL_ENTITY_TYPE_ID,
    MEETING_ENTITY_TYPE_ID,
    NOTE_ROOT_ENTITY_TYPE_ID,
    TASK_ROOT_ENTITY_TYPE_ID,
)


# ----------------------------------------------------------------------
# Helpers для построения единообразных полей
# ----------------------------------------------------------------------


def _enum_field(
    *,
    label: str,
    description: str,
    values_with_desc: list[tuple[str, str]],
) -> dict[str, Any]:
    """
    Поле типа enum с расшифровкой каждого значения в `description`.

    AI-промпт `analyze` рендерит `field.values` и `field.description` как
    есть (см. `apps/flows/bundles/crm/prompts/analyze.md`); поэтому
    значения дублируются и в `values`, и в `description` в формате
    `id — пояснение`.
    """
    if not values_with_desc:
        raise ValueError("_enum_field: values_with_desc must not be empty")
    values = [v for v, _ in values_with_desc]
    parts = "; ".join(f"`{v}` — {d}" for v, d in values_with_desc)
    full_description = f"{description.rstrip(' .')}. Значения: {parts}."
    return {
        "type": "enum",
        "label": label,
        "description": full_description,
        "values": values,
    }


def _string_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "string", "label": label, "description": description}


def _text_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "text", "label": label, "description": description}


def _date_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "date", "label": label, "description": description}


def _datetime_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "datetime", "label": label, "description": description}


def _number_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "number", "label": label, "description": description}


def _integer_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "integer", "label": label, "description": description}


def _boolean_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "boolean", "label": label, "description": description}


def _array_field(*, label: str, description: str) -> dict[str, Any]:
    return {"type": "array", "label": label, "description": description}


# ----------------------------------------------------------------------
# Ядро — SYSTEM_ENTITY_TYPE_TEMPLATES
# ----------------------------------------------------------------------


_PRIORITY_VALUES: list[tuple[str, str]] = [
    ("low", "необязательно к ближайшему сроку, можно отложить"),
    ("medium", "плановая работа без жёсткого дедлайна"),
    ("high", "важно для текущего цикла/спринта"),
    ("urgent", "горящее: блокирует команду или клиента"),
]

_EFFORT_VALUES: list[tuple[str, str]] = [
    ("xs", "до 1 часа"),
    ("s", "несколько часов в течение дня"),
    ("m", "1–2 рабочих дня"),
    ("l", "до недели"),
    ("xl", "больше недели или несколько спринтов"),
]


SYSTEM_ENTITY_TYPE_TEMPLATES: list[dict[str, Any]] = [
    {
        "type_id": NOTE_ROOT_ENTITY_TYPE_ID,
        "parent_type_id": None,
        "name": "Заметка",
        "description": (
            "Базовая заметка пользователя: свободный текст с возможными "
            "@-упоминаниями сущностей и автоматическим извлечением графа. "
            "Корень для подтипов meeting/call и любых пользовательских "
            "форматов заметок (1on1, retro и т.п.)."
        ),
        "is_system": True,
        "is_event": True,
        "prompt": (
            "Сама заметка — контейнер для текста; основной контент уже "
            "находится в `description`. В `attributes` извлекай: краткое "
            "резюме одной фразой (`summary`), вид заметки (`kind`), дату "
            "из текста (`note_date`).\n"
            "Примеры: «Поговорил с Иваном про сроки релиза» → "
            "summary='Договорились по срокам релиза', kind='free'; "
            "«Решено: запускаем 15 мая» → kind='decision_log'.\n"
            "НЕ дублируй сюда содержимое целиком — для этого есть `description` "
            "самой заметки. НЕ выдумывай дату, если она не упомянута."
        ),
        "icon": "doc-detail",
        "color": "#607D8B",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "summary": _string_field(
                label="Краткое содержание",
                description="Одно-два предложения: главная мысль или результат заметки.",
            ),
            "note_date": _date_field(
                label="Дата заметки",
                description="Календарная дата, к которой относится текст (если в самом тексте указана).",
            ),
            "kind": _enum_field(
                label="Вид заметки",
                description="Формат заметки",
                values_with_desc=[
                    ("free", "свободный текст без жёсткой структуры"),
                    ("brief", "короткий бриф/постановка по теме"),
                    ("decision_log", "журнал принятых решений"),
                    ("retro", "ретроспектива: что хорошо, что плохо, действия"),
                    ("research", "исследовательская заметка / desk research"),
                ],
            ),
        },
        "is_context_anchor": False,
        "check_duplicates": False,
    },
    {
        "type_id": MEETING_ENTITY_TYPE_ID,
        "parent_type_id": NOTE_ROOT_ENTITY_TYPE_ID,
        "name": "Встреча",
        "description": (
            "Запись о встрече: участники, повестка, принятые решения и "
            "следующие шаги. Подтип заметки — попадает в ленту заметок "
            "и в граф так же, как обычная note."
        ),
        "is_system": True,
        "is_event": True,
        "prompt": (
            "Извлекай: участников (имена/роли/компании, с разделителями), "
            "формат встречи (`meeting_kind`), место/ссылку, ключевые "
            "решения и следующие шаги с владельцами и сроками.\n"
            "Примеры: «Созвон с Acme: договорились на пилот, я готовлю "
            "оферту до пятницы» → participants='Acme team', "
            "meeting_kind='customer_call', decisions='Старт пилота', "
            "next_actions='Я: оферта до пт'.\n"
            "НЕ путай decisions и next_actions: первое — что решили, "
            "второе — что обязались сделать."
        ),
        "icon": "users",
        "color": "#4CAF50",
        "weight_coefficient": 1.2,
        "required_fields": {},
        "optional_fields": {
            "participants": _text_field(
                label="Участники",
                description="Кто был на встрече: имена, роли, компании. Разделители — запятая или перенос строки.",
            ),
            "meeting_kind": _enum_field(
                label="Формат встречи",
                description="Тип встречи по контексту",
                values_with_desc=[
                    ("standup", "ежедневный синк команды"),
                    ("planning", "планирование спринта/итерации"),
                    ("review", "демо/обзор результатов"),
                    ("retro", "ретроспектива работы команды"),
                    ("one_on_one", "встреча 1-на-1 руководитель–подчинённый"),
                    ("customer_call", "звонок/встреча с клиентом"),
                    ("partner_call", "встреча с партнёром/поставщиком"),
                    ("interview", "интервью с кандидатом"),
                    ("internal", "внутренняя рабочая встреча"),
                    ("workshop", "воркшоп/мозговой штурм"),
                    ("other", "другое: формат не подходит к списку выше"),
                ],
            ),
            "location": _string_field(
                label="Место",
                description="Адрес, переговорная или ссылка на видеозвонок (Zoom, Meet, Telemost…).",
            ),
            "start_at": _datetime_field(
                label="Время начала",
                description="Когда встреча началась (дата и время с таймзоной).",
            ),
            "duration_minutes": _integer_field(
                label="Длительность, мин",
                description="Сколько по факту длилась встреча в минутах.",
            ),
            "decisions": _text_field(
                label="Принятые решения",
                description="Что решили на встрече: каждый пункт — отдельной строкой.",
            ),
            "next_actions": _text_field(
                label="Следующие шаги",
                description="Action items: владелец и срок у каждого пункта, по одной строке.",
            ),
        },
        "is_context_anchor": False,
        "check_duplicates": False,
    },
    {
        "type_id": CALL_ENTITY_TYPE_ID,
        "parent_type_id": NOTE_ROOT_ENTITY_TYPE_ID,
        "name": "Звонок",
        "description": (
            "Запись о телефонном/голосовом разговоре: кто звонил, "
            "результат звонка, договорённости. Подтип заметки."
        ),
        "is_system": True,
        "is_event": True,
        "prompt": (
            "Извлекай: имя собеседника, направление (входящий/исходящий), "
            "результат, краткий итог разговора и длительность.\n"
            "Примеры: «Перезвонил Марине, договорились на встречу в чт» → "
            "contact_name='Марина', direction='outbound', "
            "outcome='scheduled_followup'; «Не дозвонился до Acme» → "
            "outcome='no_answer'.\n"
            "НЕ создавай отдельную сущность contact для собеседника здесь — "
            "это сделает связь mentions/linked, а не атрибут звонка."
        ),
        "icon": "phone",
        "color": "#2196F3",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "contact_name": _string_field(
                label="Собеседник",
                description="Имя человека, с которым был разговор (как он назван в тексте).",
            ),
            "direction": _enum_field(
                label="Направление",
                description="Кто инициировал звонок",
                values_with_desc=[
                    ("inbound", "входящий: позвонили нам"),
                    ("outbound", "исходящий: звонили мы"),
                ],
            ),
            "outcome": _enum_field(
                label="Результат",
                description="Чем закончился звонок",
                values_with_desc=[
                    ("connected", "соединились и поговорили"),
                    ("voicemail", "ушло на автоответчик / сообщение"),
                    ("no_answer", "не взяли трубку"),
                    ("busy", "занято"),
                    ("scheduled_followup", "договорились о следующем контакте"),
                    ("converted", "звонок привёл к сделке/договорённости"),
                    ("declined", "отказались/прервали"),
                ],
            ),
            "summary": _text_field(
                label="Итог",
                description="2–3 предложения: о чём говорили и к чему пришли.",
            ),
            "duration_minutes": _integer_field(
                label="Длительность, мин",
                description="Сколько длился разговор в минутах.",
            ),
        },
        "is_context_anchor": False,
        "check_duplicates": False,
    },
    {
        "type_id": TASK_ROOT_ENTITY_TYPE_ID,
        "parent_type_id": None,
        "name": "Задача",
        "description": (
            "Базовая задача с владельцем, сроком и статусом. Корень для "
            "доменных подтипов задач (deal-task, ticket, bug, candidate, "
            "assignment и т.п.). Карточки этого типа участвуют в досках "
            "канбана пространства."
        ),
        "is_system": True,
        "is_event": False,
        "prompt": (
            "Конкретное действие, которое кому-то нужно сделать к сроку. "
            "Извлекай: краткое название, исполнителя, дедлайн, приоритет, "
            "оценку трудозатрат.\n"
            "Примеры: «Подготовить оферту для Acme до пятницы» → "
            "title='Подготовить оферту для Acme', due_date=пятница, "
            "priority='high'; «Иван доделает миграцию на след. неделе» → "
            "assignees содержит Ивана, effort='m'.\n"
            "НЕ извлекай задачу из общих обсуждений без чёткого «нужно "
            "сделать X»: рассуждения — это note, а не task."
        ),
        "icon": "checklist",
        "color": "#FF9800",
        "weight_coefficient": 1.1,
        "required_fields": {},
        "optional_fields": {
            "title": _string_field(
                label="Название задачи",
                description="Чёткая формулировка действия в инфинитиве (что сделать).",
            ),
            "due_date": _date_field(
                label="Срок",
                description="К какой дате задача должна быть выполнена.",
            ),
            "priority": _enum_field(
                label="Приоритет",
                description="Срочность задачи относительно других",
                values_with_desc=_PRIORITY_VALUES,
            ),
            "effort": _enum_field(
                label="Оценка трудозатрат",
                description="Сколько примерно времени займёт",
                values_with_desc=_EFFORT_VALUES,
            ),
        },
        "is_context_anchor": False,
        "check_duplicates": False,
    },
    {
        "type_id": "contact",
        "parent_type_id": None,
        "name": "Контакт",
        "description": (
            "Внешний человек: клиент, партнёр, кандидат, представитель "
            "контрагента. Сотрудник своей компании на платформе — это "
            "`member`, не `contact`."
        ),
        "is_system": True,
        "is_event": False,
        "prompt": (
            "Извлекай отдельного человека с именем и контекстом "
            "взаимодействия: ФИО (или то, как его называют), роль/должность, "
            "канал связи, организация (через связь belongs_to).\n"
            "Примеры: «Иван Петров, CTO в Acme» → display_name='Иван "
            "Петров', role='CTO', + связь belongs_to к organization "
            "Acme; «Маша из ХедХантера» → display_name='Маша', добавь "
            "alias 'Маша', связь к organization.\n"
            "НЕ создавай contact для упоминания должности без имени "
            "(«звонил их юрист») и для собственных сотрудников "
            "(member-сущности уже есть среди known entities)."
        ),
        "icon": "user",
        "color": "#546E7A",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "display_name": _string_field(
                label="Имя",
                description="Как принято обращаться к человеку: ФИО или короткое имя.",
            ),
            "role": _string_field(
                label="Роль",
                description="Должность или роль в контексте (CTO, юрист, рекрутер…).",
            ),
            "email": _string_field(
                label="Email",
                description="Основной адрес электронной почты.",
            ),
            "phone": _string_field(
                label="Телефон",
                description="Основной телефон в международном формате при возможности.",
            ),
            "timezone": _string_field(
                label="Таймзона",
                description="IANA-таймзона контакта, например `Europe/Moscow`.",
            ),
            "seniority": _enum_field(
                label="Уровень",
                description="Уровень в организации",
                values_with_desc=[
                    ("ic", "individual contributor: исполнитель без подчинённых"),
                    ("lead", "тимлид/старший: ведёт небольшую группу"),
                    ("manager", "менеджер уровня команды/отдела"),
                    ("director", "директор направления"),
                    ("vp", "вице-президент / head"),
                    ("c_level", "C-уровень: CEO/CTO/CFO/COO и пр."),
                ],
            ),
            "preferred_channel": _enum_field(
                label="Предпочтительный канал",
                description="Как удобнее с ним общаться",
                values_with_desc=[
                    ("email", "электронная почта"),
                    ("phone", "телефонный звонок"),
                    ("messenger", "мессенджер: Telegram/WhatsApp/Slack"),
                    ("in_person", "очная встреча"),
                ],
            ),
            "aliases": _array_field(
                label="Псевдонимы",
                description="Альтернативные написания имени для @-упоминаний и обогащения текста.",
            ),
        },
        "is_context_anchor": False,
        "is_voice_target": True,
    },
    {
        "type_id": "member",
        "parent_type_id": None,
        "name": "Участник",
        "description": (
            "Пользователь платформы — сотрудник своей компании. Может "
            "быть автором заметок и голосом (`note_voice`). Создаётся "
            "автоматически при первом входе пользователя; не извлекается "
            "AI из текста."
        ),
        "is_system": True,
        "is_event": False,
        "prompt": "Не используется для AI-извлечения: участники приходят как known entities в analyze.",
        "extractable": False,
        "icon": "user-shield",
        "color": "#1E88E5",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "aliases": _array_field(
                label="Псевдонимы",
                description="Альтернативные имена/ники для @-упоминаний участника в тексте заметок.",
            ),
        },
        "is_context_anchor": False,
        "is_voice_target": True,
    },
    {
        "type_id": "company",
        "parent_type_id": None,
        "name": "Компания",
        "description": (
            "Своя компания-тенант на платформе. Все участники (`member`) "
            "принадлежат этой сущности. Не извлекается AI из текста — это "
            "служебная сущность платформы."
        ),
        "is_system": True,
        "is_event": False,
        "prompt": "Не используется для AI-извлечения: текущая компания приходит как known entity в analyze.",
        "extractable": False,
        "icon": "building",
        "color": "#6D4C41",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "aliases": _array_field(
                label="Псевдонимы",
                description="Названия компании, по которым она упоминается в заметках («мы», «наша команда» и официальные имена).",
            ),
        },
        "is_context_anchor": False,
    },
    {
        "type_id": "namespace",
        "parent_type_id": None,
        "name": "Пространство",
        "description": (
            "Рабочее пространство (namespace) внутри компании. Служебная "
            "сущность платформы: связывает все сущности своего "
            "пространства, появляется автоматически и не извлекается AI."
        ),
        "is_system": True,
        "is_event": False,
        "prompt": None,
        "extractable": False,
        "icon": "layers",
        "color": "#78909C",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {},
        "is_context_anchor": False,
    },
]

REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS: frozenset[str] = frozenset(
    {NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID}
)


def _namespace_template_row_from_system_spec(spec: dict) -> dict:
    parent = spec.get("parent_type_id")
    return {
        "type_id": spec["type_id"],
        "parent_type_id": parent if isinstance(parent, str) and len(parent) > 0 else None,
        "name": spec["name"],
        "description": spec.get("description"),
        "prompt": spec.get("prompt"),
        "required_fields": spec.get("required_fields") or {},
        "optional_fields": spec.get("optional_fields") or {},
        "icon": spec.get("icon"),
        "color": spec.get("color"),
        "is_event": spec.get("is_event", False),
        "check_duplicates": spec.get("check_duplicates", True),
        "weight_coefficient": spec.get("weight_coefficient", 1.0),
        "namespace_ids": spec.get("namespace_ids") or [],
        "is_context_anchor": spec.get("is_context_anchor", False),
        "is_voice_target": spec.get("is_voice_target", False),
    }


def _build_namespace_template_core_note_task_rows() -> list[dict]:
    by_id = {item["type_id"]: item for item in SYSTEM_ENTITY_TYPE_TEMPLATES}
    rows: list[dict] = []
    for tid in sorted(REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS):
        spec = by_id.get(tid)
        if spec is None:
            raise ValueError(f"SYSTEM_ENTITY_TYPE_TEMPLATES must include type_id={tid}")
        rows.append(_namespace_template_row_from_system_spec(spec))
    return rows


NAMESPACE_TEMPLATE_CORE_NOTE_TASK: list[dict] = _build_namespace_template_core_note_task_rows()


def _ensure_namespace_template_seeds_contain_core_note_task(seeds: list) -> None:
    """
    В каждом сиде гарантирует:
    - типы note и task (платформенный инвариант);
    - все parent-типы, на которые ссылаются seed-types (через
      `parent_type_id`), материализованы внутри сида. Иначе при выдаче
      списка типов нарушится parent_map (см. `entity_type_list_filter`).
    """
    core = NAMESPACE_TEMPLATE_CORE_NOTE_TASK
    system_by_id = {item["type_id"]: item for item in SYSTEM_ENTITY_TYPE_TEMPLATES}
    for seed in seeds:
        types_list = seed.get("types")
        if not isinstance(types_list, list):
            raise ValueError(f"namespace template seed {seed.get('template_id')} must have types: list")
        present = {t.get("type_id") for t in types_list if isinstance(t, dict)}
        for row in core:
            tid = row["type_id"]
            if tid not in present:
                types_list.append(dict(row))
                present.add(tid)

        # Резолв транзитивных parent_type_id → подтянуть их definition из ядра.
        pending: list[str] = []
        for spec in types_list:
            parent = spec.get("parent_type_id")
            if isinstance(parent, str) and parent and parent not in present:
                pending.append(parent)
        while pending:
            parent_id = pending.pop()
            if parent_id in present:
                continue
            parent_spec = system_by_id.get(parent_id)
            if parent_spec is None:
                raise ValueError(
                    f"namespace template seed {seed.get('template_id')!r}: "
                    f"parent_type_id={parent_id!r} ссылается на тип, отсутствующий "
                    "и в seed, и в SYSTEM_ENTITY_TYPE_TEMPLATES"
                )
            types_list.append(_namespace_template_row_from_system_spec(parent_spec))
            present.add(parent_id)
            grand_parent = parent_spec.get("parent_type_id")
            if isinstance(grand_parent, str) and grand_parent and grand_parent not in present:
                pending.append(grand_parent)


# ----------------------------------------------------------------------
# COMMON_NAMESPACE_ANCHOR_TYPES — общие якоря контекста (in_context)
# ----------------------------------------------------------------------


_HEALTH_VALUES: list[tuple[str, str]] = [
    ("green", "идёт по плану, рисков нет"),
    ("yellow", "есть риски, нужны действия, но цель достижима"),
    ("red", "под угрозой срыва, нужна эскалация"),
]


COMMON_NAMESPACE_ANCHOR_TYPES: list[dict[str, Any]] = [
    {
        "type_id": "topic",
        "name": "Тема",
        "description": (
            "Направление работы или линия разговора, к которой относятся "
            "заметки и обсуждения. Не отдельный человек и не разовое "
            "событие; используется как контекст (`in_context`) для длинных "
            "цепочек заметок."
        ),
        "prompt": (
            "Извлекай тему, если в тексте явно очерчена «область обсуждения», "
            "которая шире одной встречи: «по теме онбординга», «треки "
            "DevEx», «направление аналитики».\n"
            "Примеры: «продолжаем тему онбординга» → topic 'Онбординг'; "
            "«в треке безопасности появился вопрос» → topic 'Безопасность'.\n"
            "НЕ создавай topic для одной встречи или одной задачи — для "
            "этого есть meeting/task."
        ),
        "required_fields": {},
        "optional_fields": {
            "title": _string_field(
                label="Название темы",
                description="Короткое название направления, как принято в команде.",
            ),
            "scope": _text_field(
                label="Область",
                description="Что входит в тему и что вне её (1–3 предложения).",
            ),
            "status": _enum_field(
                label="Статус",
                description="Жизненный цикл темы",
                values_with_desc=[
                    ("active", "тема активна, по ней идёт работа и обсуждения"),
                    ("paused", "временно приостановлена, может вернуться"),
                    ("archived", "закрыта, оставлена для истории"),
                ],
            ),
        },
        "icon": "layers",
        "color": "#3949AB",
        "is_event": False,
        "check_duplicates": True,
        "is_context_anchor": True,
    },
    {
        "type_id": "organization",
        "name": "Организация",
        "description": (
            "Внешний контрагент: компания, юрлицо, агентство, поставщик, "
            "клиент. Своя компания тенанта — это служебный тип `company`, "
            "не `organization`."
        ),
        "prompt": (
            "Извлекай внешнюю организацию по упоминанию названия: бренд, "
            "юридическое имя, домен. Заполняй industry/size, если "
            "упомянуто или явно следует из контекста.\n"
            "Примеры: «Acme Corp прислали оферту» → organization 'Acme "
            "Corp'; «обсудили с командой Yandex Cloud» → organization "
            "'Yandex Cloud', industry='IT'.\n"
            "НЕ создавай organization для нашей собственной команды (для "
            "этого есть company как known entity) и для абстрактных "
            "формулировок («рынок», «отрасль»)."
        ),
        "required_fields": {},
        "optional_fields": {
            "name": _string_field(
                label="Название",
                description="Как организацию называют в тексте: бренд или короткое имя.",
            ),
            "legal_name": _string_field(
                label="Юридическое название",
                description="Полное юридическое имя (ООО «…», JSC, GmbH и т.п.).",
            ),
            "domain": _string_field(
                label="Домен",
                description="Веб-домен или email-домен организации (например `acme.com`).",
            ),
            "industry": _string_field(
                label="Отрасль",
                description="Индустрия или сегмент рынка (IT, ритейл, банки, e-commerce и т.п.).",
            ),
            "size": _enum_field(
                label="Размер",
                description="Размер организации по числу сотрудников",
                values_with_desc=[
                    ("solo", "сам себе, индивидуальный предприниматель"),
                    ("sme_1_10", "микро: 1–10 человек"),
                    ("sme_11_50", "малый бизнес: 11–50"),
                    ("mid_51_250", "средний: 51–250"),
                    ("large_251_1000", "крупный: 251–1000"),
                    ("enterprise_1000_plus", "энтерпрайз: больше 1000"),
                ],
            ),
            "country": _string_field(
                label="Страна",
                description="ISO-код или название страны главного офиса.",
            ),
        },
        "icon": "database",
        "color": "#455A64",
        "is_event": False,
        "check_duplicates": True,
        "is_context_anchor": True,
    },
    {
        "type_id": "project",
        "name": "Проект",
        "description": (
            "Инициатива с целями, владельцем и сроками. Долговременный "
            "якорь контекста для заметок и задач, относящихся к одной "
            "целевой работе."
        ),
        "prompt": (
            "Извлекай проект, если в тексте есть имя инициативы, цель и/или "
            "владелец. Заполняй status и health, если они однозначно "
            "следуют из текста.\n"
            "Примеры: «по проекту Atlas стартуем discovery» → project "
            "'Atlas', status='discovery'; «проект Phoenix — красный, нужен "
            "эскалейт» → project 'Phoenix', health='red', status='blocked'.\n"
            "НЕ создавай project для абстрактных «работ» без имени и для "
            "одной задачи."
        ),
        "required_fields": {},
        "optional_fields": {
            "title": _string_field(
                label="Название",
                description="Имя проекта/инициативы как принято в команде.",
            ),
            "objective": _text_field(
                label="Цель",
                description="Какой результат должен принести проект (1–3 предложения).",
            ),
            "status": _enum_field(
                label="Статус",
                description="Текущая стадия проекта",
                values_with_desc=[
                    ("discovery", "идёт исследование, требования формируются"),
                    ("in_progress", "активная разработка/исполнение"),
                    ("blocked", "заблокирован: ждёт решения или ресурса"),
                    ("done", "завершён, цели достигнуты"),
                    ("cancelled", "отменён, цели не достигнуты"),
                ],
            ),
            "health": _enum_field(
                label="Здоровье",
                description="Сводный сигнал о ходе проекта",
                values_with_desc=_HEALTH_VALUES,
            ),
            "start_date": _date_field(
                label="Старт",
                description="Дата старта проекта.",
            ),
            "end_date": _date_field(
                label="Завершение",
                description="Плановая или фактическая дата завершения.",
            ),
        },
        "icon": "folder",
        "color": "#5E35B1",
        "is_event": False,
        "check_duplicates": True,
        "is_context_anchor": True,
    },
]


# ----------------------------------------------------------------------
# SYSTEM_RELATIONSHIP_TYPE_TEMPLATES — типы связей графа
# ----------------------------------------------------------------------


SYSTEM_RELATIONSHIP_TYPE_TEMPLATES: list[dict[str, Any]] = [
    {
        "type_id": "mentions",
        "name": "Упоминает",
        "description": "Упоминание сущности в тексте без явной @-ссылки (выявляет AI).",
        "is_system": True,
        "is_directed": True,
        "prompt": (
            "Когда использовать: текст ссылается на entity по имени, но "
            "автор не поставил @-токен (этим занимается тип `linked`). "
            "Источник связи — заметка/задача, цель — упомянутая entity.\n"
            "Примеры:\n"
            "- «Обсудили проект с Иваном» → note mentions contact 'Иван'.\n"
            "- «Позвонил в Acme Corp по сделке Q3» → note mentions "
            "  organization 'Acme Corp'; note mentions deal 'Q3'.\n"
            "- «Задача по сделке XYZ» → task mentions deal 'XYZ'.\n"
            "Когда НЕ использовать: для явных @-ссылок (тип `linked`); "
            "для собственного автора (он будет связан через `note_voice`); "
            "для якоря заметки (используй `in_context`)."
        ),
        "icon": "chat",
        "color": "#9E9E9E",
        "weight_default": 0.5,
    },
    {
        "type_id": "linked",
        "name": "Явная ссылка",
        "description": "Прямая ссылка на entity через @-токен в тексте; формирует сервис, не AI.",
        "is_system": True,
        "is_directed": True,
        "prompt": None,
        "icon": "circular-connection",
        "color": "#2196F3",
        "weight_default": 1.0,
    },
    {
        "type_id": "related_to",
        "name": "Связан с",
        "description": "Общая ассоциация двух сущностей без явной иерархии или направления.",
        "is_system": True,
        "is_directed": False,
        "prompt": (
            "Когда использовать: две сущности связаны общим контекстом, "
            "но более точного типа из списка нет.\n"
            "Примеры:\n"
            "- «Проект Alpha связан с инициативой Beta» → project "
            "  related_to project.\n"
            "- «Клиент интересуется новым продуктом» → contact related_to "
            "  product.\n"
            "- Два контакта упомянуты вместе в одном контексте → contact "
            "  related_to contact.\n"
            "Когда НЕ использовать: если подходит более точный тип "
            "(`parent_of`, `assigned_to`, `belongs_to`, `follows_up`, "
            "`blocks`, `reports_to`)."
        ),
        "icon": "link",
        "color": "#78909C",
        "weight_default": 0.7,
    },
    {
        "type_id": "parent_of",
        "name": "Родитель",
        "description": "Иерархия: одна сущность является контейнером/родителем для другой.",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "child_of",
        "prompt": (
            "Когда использовать: одна сущность по смыслу содержит другую "
            "(epic→story, organization→department, project→task).\n"
            "Примеры:\n"
            "- «Проект включает задачу» → project parent_of task.\n"
            "- «Отдел продаж входит в Acme» → organization 'Acme' "
            "  parent_of organization 'Sales'.\n"
            "- «Эпик содержит несколько user stories» → epic parent_of "
            "  user_story.\n"
            "Когда НЕ использовать: для назначения исполнителя "
            "(`assigned_to`); для членства человека в организации "
            "(`belongs_to`); для блокеров (`blocks`).\n"
            "Обратная связь `child_of` создаётся автоматически."
        ),
        "icon": "tree-square-dot",
        "color": "#5C6BC0",
        "weight_default": 1.0,
    },
    {
        "type_id": "child_of",
        "name": "Дочерний",
        "description": "Обратная сторона `parent_of`; создаётся автоматически.",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "parent_of",
        "prompt": None,
        "icon": "tree-square-dot",
        "color": "#5C6BC0",
        "weight_default": 1.0,
    },
    {
        "type_id": "assigned_to",
        "name": "Назначено",
        "description": "Задача/инцидент/тикет назначены на конкретного человека или команду.",
        "is_system": True,
        "is_directed": True,
        "prompt": (
            "Когда использовать: текст явно говорит, что некий объект "
            "работы (задача, тикет, инцидент, кандидат на роль) поручен "
            "конкретному человеку/команде.\n"
            "Примеры:\n"
            "- «Задачу поручили Ивану» → task assigned_to contact 'Иван'.\n"
            "- «Тикет назначен на дежурного» → ticket assigned_to member.\n"
            "- «На интервью со студентом отправлен Лид» → interview "
            "  assigned_to member 'Лид'.\n"
            "Когда НЕ использовать: для владельца стратегического объекта "
            "(`owner_of`); для членства в орге (`belongs_to`); если "
            "только обсуждали кандидатов на исполнителя без назначения."
        ),
        "icon": "user",
        "color": "#26A69A",
        "weight_default": 0.8,
    },
    {
        "type_id": "belongs_to",
        "name": "Принадлежит",
        "description": "Членство/принадлежность: человек работает в организации, объект относится к контексту.",
        "is_system": True,
        "is_directed": True,
        "prompt": (
            "Когда использовать: один объект логически принадлежит "
            "другому (контакт ↔ организация, сделка ↔ организация, "
            "контракт ↔ matter).\n"
            "Примеры:\n"
            "- «Иван работает в Acme Corp» → contact 'Иван' belongs_to "
            "  organization 'Acme Corp'.\n"
            "- «Сделка относится к отделу продаж» → deal belongs_to "
            "  organization 'Sales'.\n"
            "- «Кандидат пришёл из компании XYZ» → contact belongs_to "
            "  organization 'XYZ'.\n"
            "Когда НЕ использовать: для назначения задачи (`assigned_to`); "
            "для иерархии «целое-часть» одной природы (`parent_of`); для "
            "владения объектом (`owner_of`)."
        ),
        "icon": "folder",
        "color": "#8D6E63",
        "weight_default": 0.8,
    },
    {
        "type_id": "follows_up",
        "name": "Продолжение",
        "description": "Последовательная цепочка: одна сущность является продолжением другой.",
        "is_system": True,
        "is_directed": True,
        "prompt": (
            "Когда использовать: текущая запись развивает или продолжает "
            "ранее заведённую (повторная встреча по теме, follow-up "
            "звонок, follow-up задача после совещания).\n"
            "Примеры:\n"
            "- «Продолжение вчерашнего обсуждения» → note follows_up "
            "  предыдущая note.\n"
            "- «Повторная встреча по сделке Acme» → meeting follows_up "
            "  предыдущая meeting.\n"
            "- «Задача по итогам совещания» → task follows_up note.\n"
            "Когда НЕ использовать: для иерархии (`parent_of`); для "
            "блокирования (`blocks`); для общего контекста (`in_context`)."
        ),
        "icon": "arrow-right",
        "color": "#42A5F5",
        "weight_default": 0.6,
    },
    {
        "type_id": "blocks",
        "name": "Блокирует",
        "description": "Зависимость: исходная сущность блокирует выполнение целевой.",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "blocked_by",
        "prompt": (
            "Когда использовать: пока не сделана/не разрешена сущность A, "
            "нельзя двигать сущность B (зависимости задач, инцидентов, "
            "сделок).\n"
            "Примеры:\n"
            "- «Нельзя начать деплой пока не пройдут тесты» → task "
            "  'тесты' blocks task 'деплой'.\n"
            "- «Сделка ждёт юридическую проверку» → task 'юр. проверка' "
            "  blocks deal.\n"
            "- «Релиз ждёт фикса бага» → bug blocks release.\n"
            "Когда НЕ использовать: для последовательности без жёсткой "
            "зависимости (`follows_up`); для иерархии (`parent_of`).\n"
            "Обратная связь `blocked_by` создаётся автоматически."
        ),
        "icon": "error",
        "color": "#EF5350",
        "weight_default": 0.9,
    },
    {
        "type_id": "blocked_by",
        "name": "Заблокировано",
        "description": "Обратная сторона `blocks`; создаётся автоматически.",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "blocks",
        "prompt": None,
        "icon": "error",
        "color": "#EF5350",
        "weight_default": 0.9,
    },
    {
        "type_id": "duplicates",
        "name": "Дубликат",
        "description": "Маркировка дубликата сущности; не задаёт направления.",
        "is_system": True,
        "is_directed": False,
        "prompt": None,
        "icon": "copy",
        "color": "#BDBDBD",
        "weight_default": 0.3,
    },
    {
        "type_id": "reports_to",
        "name": "Подчиняется",
        "description": "Иерархия людей: подчинённый → руководитель.",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "manages",
        "prompt": (
            "Когда использовать: текст явно говорит, что один человек "
            "находится в подчинении у другого (организационная иерархия).\n"
            "Примеры:\n"
            "- «Иван — мой подчинённый» → contact 'Иван' reports_to "
            "  member текущего автора.\n"
            "- «Отдел Маши состоит из 5 человек» → contact 'Маша' "
            "  reports_to (упомянутый руководитель).\n"
            "- «Анна — head of design, ей подчиняется команда из 8» → "
            "  caждый contact команды reports_to contact 'Анна'.\n"
            "Когда НЕ использовать: для членства в орге без иерархии "
            "(`belongs_to`); для проектного назначения задачи "
            "(`assigned_to`).\n"
            "Обратная связь `manages` создаётся автоматически."
        ),
        "icon": "user-shield",
        "color": "#7E57C2",
        "weight_default": 0.9,
    },
    {
        "type_id": "manages",
        "name": "Руководит",
        "description": "Обратная сторона `reports_to`; создаётся автоматически.",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "reports_to",
        "prompt": None,
        "icon": "user-shield",
        "color": "#7E57C2",
        "weight_default": 0.9,
    },
    {
        "type_id": "owner_of",
        "name": "Владелец",
        "description": "Долговременный ответственный за объект работы (проект, сделка, инцидент, инициатива).",
        "is_system": True,
        "is_directed": True,
        "prompt": (
            "Когда использовать: человек назначен ответственным за объект "
            "целиком, а не за разовую задачу. Применяй к проектам, "
            "сделкам, инициативам, инцидентам, продуктовым фичам.\n"
            "Примеры:\n"
            "- «Проект Atlas ведёт Маша» → contact 'Маша' owner_of "
            "  project 'Atlas'.\n"
            "- «За сделку Acme отвечаю я» → member текущего автора "
            "  owner_of deal 'Acme'.\n"
            "- «Инцидент SEV1 эскалирован на дежурного SRE» → contact "
            "  'дежурный SRE' owner_of incident.\n"
            "Когда НЕ использовать: для разовой задачи (`assigned_to`); "
            "для членства в орге (`belongs_to`)."
        ),
        "icon": "user",
        "color": "#00897B",
        "weight_default": 0.85,
    },
    {
        "type_id": "attended",
        "name": "Присутствовал",
        "description": "Контакт/участник присутствовал на встрече; формируется сервисом из participants.",
        "is_system": True,
        "is_directed": True,
        "prompt": None,
        "icon": "users",
        "color": "#7CB342",
        "weight_default": 0.7,
    },
    {
        "type_id": "note_voice",
        "name": "Голос заметки",
        "description": "Заметка → сущность-голос (от чьего имени написана); сервисная связь.",
        "is_system": True,
        "is_directed": True,
        "prompt": None,
        "icon": "user",
        "color": "#7CB342",
        "weight_default": 1.0,
    },
    {
        "type_id": "in_context",
        "name": "В контексте",
        "description": (
            "Заметка привязана к якорю контекста: тема, проект, "
            "организация или объект работы (сделка, инцидент). Не к "
            "заметке и не к отдельному контакту."
        ),
        "is_system": True,
        "is_directed": True,
        "prompt": None,
        "icon": "anchor",
        "color": "#5C6BC0",
        "weight_default": 1.0,
    },
]


# ----------------------------------------------------------------------
# Общие fragments для seed-пакетов
# ----------------------------------------------------------------------


def _account_tier_field() -> dict[str, Any]:
    return _enum_field(
        label="Категория клиента",
        description="Стратегическая значимость для бизнеса",
        values_with_desc=[
            ("strategic", "флагман, top-3 по выручке/влиянию"),
            ("key", "ключевой клиент с регулярной выручкой"),
            ("regular", "обычный клиент"),
            ("trial", "пилот / триал, выручка ещё не подтверждена"),
        ],
    )


def _currency_field() -> dict[str, Any]:
    return _enum_field(
        label="Валюта",
        description="Валюта суммы",
        values_with_desc=[
            ("RUB", "российский рубль"),
            ("USD", "доллар США"),
            ("EUR", "евро"),
            ("CNY", "китайский юань"),
            ("KZT", "казахстанский тенге"),
            ("AED", "дирхам ОАЭ"),
            ("GBP", "британский фунт"),
        ],
    )


# ----------------------------------------------------------------------
# Seed: sales (B2B-CRM)
# ----------------------------------------------------------------------


_SEED_SALES = {
    "template_id": "sales",
    "name": "B2B-продажи",
    "description": (
        "Полный B2B-CRM: лиды, аккаунты и сделки с воронками BANT/MEDDIC, "
        "контакты с decision-роли, котировки и задачи. Подходит для "
        "длинных циклов сделок с несколькими стейкхолдерами."
    ),
    "icon": "chart",
    "types": [
        {
            "type_id": "lead",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Лид",
            "description": (
                "Потенциальная возможность до квалификации: интерес к "
                "продукту, не подтверждённый бюджетом и сроком. Цель — "
                "перевести в `deal` или дисквалифицировать."
            ),
            "prompt": (
                "Извлекай новые источники интереса с указанием канала и "
                "минимальных BANT-полей: бюджет, ЛПР, потребность, сроки.\n"
                "Примеры: «Заявка с сайта от Acme на 50 лицензий, "
                "до конца квартала» → lead source='inbound', "
                "stage='qualified', need='50 лицензий', timeline='Q', "
                "+ belongs_to organization Acme.\n"
                "НЕ создавай lead для уже подтверждённых сделок (это "
                "сразу `deal`) и для разовых вопросов в саппорт."
            ),
            "required_fields": {
                "stage": _enum_field(
                    label="Стадия",
                    description="Воронка квалификации лида",
                    values_with_desc=[
                        ("new", "только пришёл, не обработан"),
                        ("working", "в работе: первичный контакт сделан"),
                        ("qualified", "квалифицирован: подходит, передаём в сделку"),
                        ("disqualified", "не подходит: не наш профиль / нет потребности"),
                        ("nurture", "сейчас не готов, ведём к следующему циклу"),
                    ],
                ),
                "source": _enum_field(
                    label="Источник",
                    description="Канал, по которому пришёл лид",
                    values_with_desc=[
                        ("inbound", "входящий: сам пришёл (сайт, email)"),
                        ("outbound", "исходящий: cold-outreach"),
                        ("referral", "рекомендация существующего клиента"),
                        ("partner", "партнёрский канал"),
                        ("event", "конференция/ивент"),
                        ("marketing", "маркетинговая кампания"),
                        ("other", "другой канал"),
                    ],
                ),
            },
            "optional_fields": {
                "budget": _number_field(
                    label="Бюджет",
                    description="Оценочный бюджет клиента (B из BANT) в основной валюте.",
                ),
                "authority": _string_field(
                    label="ЛПР",
                    description="Кто принимает решение (Authority в BANT): имя/роль.",
                ),
                "need": _text_field(
                    label="Потребность",
                    description="Что клиент хочет решить (Need в BANT).",
                ),
                "timeline": _string_field(
                    label="Срок",
                    description="Когда клиент хочет внедрить решение (Timeline в BANT).",
                ),
                "disqualification_reason": _string_field(
                    label="Причина отказа",
                    description="Если stage=disqualified — почему клиент не подходит.",
                ),
            },
            "icon": "target-lock",
            "color": "#7E57C2",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "account",
            "name": "Аккаунт",
            "description": (
                "Долговременный клиент-организация с историей сделок. "
                "Контейнер для нескольких `deal` одного клиента; "
                "используется в Account-Based Selling."
            ),
            "prompt": (
                "Извлекай аккаунт, если в тексте упоминается клиент с "
                "повторными сделками или долгосрочным контрактом.\n"
                "Примеры: «Acme — наш стратег, MRR $50k» → account 'Acme', "
                "tier='strategic'; «Beta пилот завершён, переходим на "
                "пейд» → account 'Beta', tier='trial'.\n"
                "НЕ создавай account для разового лида — для этого есть "
                "lead. Аккаунт появляется, когда клиент уже на платформе."
            ),
            "required_fields": {},
            "optional_fields": {
                "tier": _account_tier_field(),
                "mrr": _number_field(
                    label="MRR",
                    description="Месячная регулярная выручка от аккаунта.",
                ),
                "currency": _currency_field(),
                "owner_role": _string_field(
                    label="Account Manager",
                    description="Имя ответственного аккаунт-менеджера или CSM.",
                ),
                "renewal_date": _date_field(
                    label="Дата пересмотра контракта",
                    description="Ближайший рубеж продления / пересогласования контракта.",
                ),
            },
            "icon": "building",
            "color": "#26A69A",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "deal",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Сделка",
            "description": (
                "Конкретная коммерческая возможность с суммой, стадией и "
                "вероятностью закрытия. Якорь для всех заметок и задач "
                "по этой сделке."
            ),
            "prompt": (
                "Извлекай сделку по упоминанию суммы/стадии/срока "
                "закрытия. Если в тексте указана организация-клиент — "
                "построй belongs_to к organization/account.\n"
                "Примеры: «Сделка Acme на $80k, дискавери» → deal "
                "'Acme - $80k', amount=80000, currency='USD', "
                "stage='discovery'; «Закрыли Beta deal на пилот» → "
                "stage='closed_won'.\n"
                "НЕ создавай deal для абстрактных «возможностей» без "
                "клиента и для одноразовых консультаций."
            ),
            "required_fields": {
                "stage": _enum_field(
                    label="Стадия сделки",
                    description="Стадия воронки продаж",
                    values_with_desc=[
                        ("discovery", "первичное исследование потребности"),
                        ("proposal", "сделано предложение / отправлено КП"),
                        ("negotiation", "переговоры по условиям"),
                        ("contract", "подготовка/подписание контракта"),
                        ("closed_won", "закрыта успешно"),
                        ("closed_lost", "проиграна"),
                    ],
                ),
            },
            "optional_fields": {
                "amount": _number_field(
                    label="Сумма",
                    description="Общая сумма сделки в выбранной валюте.",
                ),
                "currency": _currency_field(),
                "probability": _integer_field(
                    label="Вероятность, %",
                    description="Оценочная вероятность закрытия от 0 до 100.",
                ),
                "expected_close_date": _date_field(
                    label="Ожидаемое закрытие",
                    description="Когда планируется подписать или потерять сделку.",
                ),
                "lost_reason": _enum_field(
                    label="Причина проигрыша",
                    description="Если stage=closed_lost — почему",
                    values_with_desc=[
                        ("price", "цена выше бюджета"),
                        ("competitor", "выбрали конкурента"),
                        ("no_decision", "клиент так и не решил"),
                        ("no_budget", "пропал бюджет"),
                        ("timing", "сейчас не вовремя"),
                        ("product_gap", "не хватает функционала"),
                        ("other", "другая причина"),
                    ],
                ),
                "next_step": _string_field(
                    label="Следующий шаг",
                    description="Что нужно сделать на следующей итерации сделки.",
                ),
            },
            "icon": "chart-multifunction",
            "color": "#EF6C00",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "quote",
            "name": "Котировка",
            "description": (
                "Коммерческое предложение / прайс-лист с фиксированной "
                "суммой и сроком действия. Принадлежит конкретной сделке."
            ),
            "prompt": (
                "Извлекай отправленные клиенту КП/расчёты с суммой и "
                "сроком действия.\n"
                "Примеры: «Отправил оферту на $25k, действительна до "
                "30 июня» → quote total=25000, currency='USD', "
                "valid_until=2024-06-30, status='sent'.\n"
                "НЕ создавай quote для устных «прикинули цифру» без "
                "оформленного предложения."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Состояние коммерческого предложения",
                    values_with_desc=[
                        ("draft", "черновик: ещё не отправлено"),
                        ("sent", "отправлено клиенту"),
                        ("accepted", "принято клиентом"),
                        ("rejected", "отклонено клиентом"),
                        ("expired", "срок действия истёк"),
                    ],
                ),
            },
            "optional_fields": {
                "total": _number_field(
                    label="Сумма",
                    description="Итоговая сумма КП.",
                ),
                "currency": _currency_field(),
                "valid_until": _date_field(
                    label="Действительно до",
                    description="Срок, после которого КП теряет силу.",
                ),
                "discount_pct": _number_field(
                    label="Скидка, %",
                    description="Скидка относительно прайса (0–100).",
                ),
            },
            "icon": "doc-detail",
            "color": "#FB8C00",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "contact",
            "name": "Контакт",
            "description": (
                "Контакт со стороны клиента в B2B-сделке с decision-ролью "
                "по MEDDIC/Challenger. Наследует базовый контакт + поле "
                "роли в принятии решения."
            ),
            "prompt": (
                "Извлекай человека со стороны клиента: имя, роль, "
                "decision-функцию (если в тексте читается).\n"
                "Примеры: «Иван — CTO, решает по техстеку» → "
                "decision_role='economic_buyer'; «Маша провела "
                "тех.экспертизу, дала добро» → decision_role='champion'.\n"
                "НЕ ставь decision_role, если по тексту нельзя её "
                "однозначно определить."
            ),
            "required_fields": {},
            "optional_fields": {
                "display_name": _string_field(
                    label="Имя",
                    description="ФИО контакта или короткое имя.",
                ),
                "role": _string_field(
                    label="Должность",
                    description="Должность в компании клиента (CTO, head of …, buyer и т.п.).",
                ),
                "email": _string_field(label="Email", description="Рабочий адрес контакта."),
                "phone": _string_field(label="Телефон", description="Рабочий телефон контакта."),
                "decision_role": _enum_field(
                    label="Роль в принятии решения",
                    description="Роль по MEDDIC/Challenger",
                    values_with_desc=[
                        ("economic_buyer", "финальный распорядитель бюджета"),
                        ("champion", "внутренний адвокат, продаёт за нас внутри"),
                        ("influencer", "влияет на решение, но не подписывает"),
                        ("user", "конечный пользователь продукта"),
                        ("blocker", "блокирует сделку (юристы, безопасность, IT)"),
                        ("unknown", "роль пока не понятна"),
                    ],
                ),
                "aliases": _array_field(
                    label="Псевдонимы",
                    description="Альтернативные написания имени для @-упоминаний.",
                ),
            },
            "icon": "user",
            "color": "#546E7A",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
            "is_voice_target": True,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#9E9E9E"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:lead": {
                "stages": [
                    {"id": "new", "label": "Новый", "color": "#90A4AE"},
                    {"id": "working", "label": "В работе", "color": "#42A5F5"},
                    {"id": "qualified", "label": "Квалифицирован", "color": "#7E57C2"},
                    {"id": "disqualified", "label": "Не подходит", "color": "#BDBDBD"},
                    {"id": "nurture", "label": "На дозревание", "color": "#FFB74D"},
                ]
            },
            "task:deal": {
                "stages": [
                    {"id": "discovery", "label": "Discovery", "color": "#90A4AE"},
                    {"id": "proposal", "label": "Предложение", "color": "#42A5F5"},
                    {"id": "negotiation", "label": "Переговоры", "color": "#7E57C2"},
                    {"id": "contract", "label": "Контракт", "color": "#FB8C00"},
                    {"id": "closed_won", "label": "Закрыта 🎉", "color": "#66BB6A"},
                    {"id": "closed_lost", "label": "Проиграна", "color": "#BDBDBD"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: agile_project (Scrum / Kanban)
# ----------------------------------------------------------------------


_SEED_AGILE = {
    "template_id": "agile_project",
    "name": "Agile-проект",
    "description": (
        "Scrum/Kanban-команда: эпики, спринты, релизы, user stories, "
        "баги, помехи, спайки и персоны. Готовые доски для user_story, "
        "bug, spike и общая task-доска."
    ),
    "icon": "chart-multifunction",
    "types": [
        {
            "type_id": "epic",
            "name": "Эпик",
            "description": (
                "Крупная инициатива, разбиваемая на user stories. Якорь "
                "для всех заметок и задач, относящихся к эпику."
            ),
            "prompt": (
                "Извлекай эпик, если в тексте упоминается крупная "
                "целевая работа на несколько спринтов с именем и "
                "владельцем. Заполняй status и priority при возможности.\n"
                "Примеры: «Эпик Onboarding — discovery, ведёт Маша» → "
                "epic 'Onboarding', status='discovery', + owner_of "
                "contact 'Маша'.\n"
                "НЕ создавай эпик для одной фичи или одной user story — "
                "для них есть feature/user_story."
            ),
            "required_fields": {},
            "optional_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Стадия жизненного цикла эпика",
                    values_with_desc=[
                        ("discovery", "идея исследуется, требования уточняются"),
                        ("ready", "готов к разработке: требования и AC согласованы"),
                        ("in_progress", "активная разработка"),
                        ("done", "завершён, цели достигнуты"),
                        ("cancelled", "отменён"),
                    ],
                ),
                "priority": _enum_field(
                    label="Приоритет",
                    description="Бизнес-приоритет эпика",
                    values_with_desc=[
                        ("low", "может подождать"),
                        ("medium", "плановый бэклог"),
                        ("high", "важно для квартала"),
                        ("critical", "блокирует стратегические цели"),
                    ],
                ),
                "objective": _text_field(
                    label="Цель",
                    description="Какой бизнес-результат должен принести эпик (1–3 предложения).",
                ),
            },
            "icon": "layers",
            "color": "#6A1B9A",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "sprint",
            "name": "Спринт",
            "description": (
                "Итерация фиксированной длительности с целью спринта "
                "(Sprint Goal по Scrum Guide). Якорь для заметок о "
                "планировании, ретроспективе и review."
            ),
            "prompt": (
                "Извлекай спринт по упоминанию номера/цели/дат "
                "(planning/review/retro по конкретному спринту).\n"
                "Примеры: «Sprint 23 закрылся, цель не выполнена на 30%» "
                "→ sprint number=23, status='completed'; «На планирование "
                "Sprint 24 — 12 марта» → sprint number=24, status="
                "'planning', start_date=2024-03-12.\n"
                "НЕ создавай спринт для общей задачи без явной "
                "итерации/номера."
            ),
            "required_fields": {},
            "optional_fields": {
                "goal": _text_field(
                    label="Цель спринта",
                    description="Sprint Goal: одно утверждение, что команда хочет достичь.",
                ),
                "number": _integer_field(
                    label="Номер",
                    description="Порядковый номер спринта от старта проекта.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл спринта",
                    values_with_desc=[
                        ("planning", "идёт планирование"),
                        ("active", "спринт запущен"),
                        ("completed", "спринт завершён"),
                    ],
                ),
                "start_date": _date_field(label="Старт", description="Дата начала спринта."),
                "end_date": _date_field(
                    label="Конец",
                    description="Дата окончания спринта (день демо/ретро).",
                ),
            },
            "icon": "circular-connection",
            "color": "#1565C0",
            "is_event": True,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "release",
            "name": "Релиз",
            "description": (
                "Инкремент продукта, выпущенный в прод. Якорь для "
                "changelog-заметок и постмортемов."
            ),
            "prompt": (
                "Извлекай релиз по версии и дате выпуска.\n"
                "Примеры: «Выкатили 2.4.0 в прод 12 апреля» → release "
                "version='2.4.0', release_date=2024-04-12, "
                "status='released'.\n"
                "НЕ создавай релиз без версии или для разовых hotfix-"
                "правок (для них bug/incident)."
            ),
            "required_fields": {},
            "optional_fields": {
                "version": _string_field(
                    label="Версия",
                    description="Семантическая версия (например `2.4.0`, `v3.0-beta`).",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл релиза",
                    values_with_desc=[
                        ("planned", "запланирован"),
                        ("released", "выпущен в прод"),
                        ("rolled_back", "откатили после релиза"),
                        ("deprecated", "устаревший, не поддерживается"),
                    ],
                ),
                "release_date": _date_field(
                    label="Дата выпуска",
                    description="Фактическая или плановая дата выхода в прод.",
                ),
            },
            "icon": "chart",
            "color": "#2E7D32",
            "is_event": True,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "persona",
            "name": "Персона",
            "description": (
                "Образ целевого пользователя продукта. Якорь для "
                "user stories и UX-заметок, помогает не путать сегменты."
            ),
            "prompt": (
                "Извлекай персону по упоминанию роли пользователя с "
                "целями и/или болями.\n"
                "Примеры: «менеджер по продажам, ищет CRM-замену» → "
                "persona role='менеджер по продажам', goals='Найти "
                "CRM-замену'.\n"
                "НЕ создавай персону для конкретного человека (это "
                "contact); для одной user story (это user_story)."
            ),
            "required_fields": {},
            "optional_fields": {
                "role": _string_field(
                    label="Роль",
                    description="Сегмент или профессиональная роль пользователя.",
                ),
                "goals": _text_field(
                    label="Цели",
                    description="Что персона хочет достичь, используя продукт.",
                ),
                "pain_points": _text_field(
                    label="Боли",
                    description="Текущие проблемы и фрустрации до появления продукта.",
                ),
            },
            "icon": "user",
            "color": "#00695C",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "user_story",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "User Story",
            "description": (
                "История в формате «Как [роль] я хочу [действие], чтобы "
                "[ценность]». Подтип задачи: попадает в доску user_story."
            ),
            "prompt": (
                "Извлекай конкретные пользовательские истории с "
                "ролью/действием/ценностью и критериями приёмки.\n"
                "Примеры: «Как админ я хочу видеть аудит, чтобы "
                "проверять права» → user_story с этим текстом, "
                "story_points=3.\n"
                "НЕ создавай user_story для технических задач без "
                "пользовательской ценности — для этого есть task / "
                "task:dev_task."
            ),
            "required_fields": {},
            "optional_fields": {
                "acceptance_criteria": _text_field(
                    label="Критерии приёмки",
                    description="Условия Definition of Done для конкретной истории.",
                ),
                "story_points": _integer_field(
                    label="Story Points",
                    description="Оценка сложности по Fibonacci (1, 2, 3, 5, 8, 13…).",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Стадия в доске user_story",
                    values_with_desc=[
                        ("backlog", "не готова к спринту"),
                        ("ready", "готова к взятию (Definition of Ready)"),
                        ("in_progress", "в работе"),
                        ("in_review", "на ревью / тестировании"),
                        ("done", "принята"),
                        ("cancelled", "отменена"),
                    ],
                ),
            },
            "icon": "doc-detail",
            "color": "#4527A0",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "bug",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Баг",
            "description": (
                "Дефект в продукте: расхождение между ожидаемым и "
                "фактическим поведением. Подтип задачи с собственной "
                "доской по жизненному циклу бага."
            ),
            "prompt": (
                "Извлекай дефекты с явным описанием воспроизведения "
                "и оценкой severity/reproducibility.\n"
                "Примеры: «Падает экспорт CSV для клиентов >10k строк» → "
                "bug severity='major', reproducibility='always'.\n"
                "НЕ создавай bug для feature-request — для них task/"
                "user_story."
            ),
            "required_fields": {},
            "optional_fields": {
                "severity": _enum_field(
                    label="Серьёзность",
                    description="Влияние бага на пользователей",
                    values_with_desc=[
                        ("blocker", "блокирует ключевой сценарий"),
                        ("critical", "ломает важный функционал, обходного пути нет"),
                        ("major", "ощутимая проблема, есть workaround"),
                        ("minor", "мелкое неудобство"),
                        ("trivial", "косметика / опечатки"),
                    ],
                ),
                "reproducibility": _enum_field(
                    label="Воспроизводимость",
                    description="Как часто баг повторяется",
                    values_with_desc=[
                        ("always", "стабильно воспроизводится"),
                        ("sometimes", "иногда: при определённых условиях"),
                        ("rare", "редко, не удаётся стабильно поймать"),
                    ],
                ),
                "environment": _string_field(
                    label="Окружение",
                    description="Где баг проявляется: prod/staging, версия, ОС, браузер.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл бага",
                    values_with_desc=[
                        ("open", "заведён, не разобран"),
                        ("triaged", "разобран, оценён, принят в работу"),
                        ("in_progress", "в работе"),
                        ("fixed", "пофикшен, ждёт верификации"),
                        ("verified", "проверен на стейдже"),
                        ("closed", "закрыт"),
                        ("wont_fix", "решено не исправлять"),
                    ],
                ),
            },
            "icon": "error",
            "color": "#C62828",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "impediment",
            "name": "Помеха",
            "description": (
                "Блокер или препятствие, мешающее команде достичь цели "
                "спринта. Не задача — это сигнал для Scrum Master."
            ),
            "prompt": (
                "Извлекай явные блокеры команды с severity и статусом "
                "устранения.\n"
                "Примеры: «Не дают доступ к staging — встал тест» → "
                "impediment severity='major', status='open'.\n"
                "НЕ путай impediment с bug: impediment мешает команде, "
                "bug — дефект продукта."
            ),
            "required_fields": {},
            "optional_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Стадия устранения помехи",
                    values_with_desc=[
                        ("open", "обнаружена, ещё не решается"),
                        ("in_progress", "Scrum Master/тимлид работает над устранением"),
                        ("resolved", "устранена"),
                    ],
                ),
                "severity": _enum_field(
                    label="Серьёзность",
                    description="Масштаб помехи",
                    values_with_desc=[
                        ("minor", "замедляет работу одного человека"),
                        ("major", "блокирует одну задачу или фичу"),
                        ("critical", "блокирует весь спринт или цель команды"),
                    ],
                ),
            },
            "icon": "error",
            "color": "#B71C1C",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "spike",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Спайк",
            "description": (
                "Исследовательская задача с тайм-боксом для снятия "
                "технической или продуктовой неопределённости. Подтип "
                "задачи."
            ),
            "prompt": (
                "Извлекай спайк, если в тексте есть исследовательский "
                "вопрос с временным ограничением.\n"
                "Примеры: «Разобраться 2 дня с Kafka vs Pulsar» → spike "
                "time_box='2 дня', outcome='решение по брокеру'.\n"
                "НЕ создавай spike для обычной задачи реализации."
            ),
            "required_fields": {},
            "optional_fields": {
                "time_box": _string_field(
                    label="Тайм-бокс",
                    description="Максимальное время на исследование (`2 дня`, `1 спринт`).",
                ),
                "outcome": _text_field(
                    label="Ожидаемый результат",
                    description="Какой артефакт должен появиться: документ, прототип, решение.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл спайка",
                    values_with_desc=[
                        ("proposed", "предложен, ждёт планирования"),
                        ("time_boxed", "взят в работу с тайм-боксом"),
                        ("completed", "завершён, есть результат"),
                        ("discarded", "отброшен: ответ не нужен / получен другим путём"),
                    ],
                ),
            },
            "icon": "target-lock",
            "color": "#37474F",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "Backlog", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "in_review", "label": "На ревью", "color": "#7E57C2"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:user_story": {
                "stages": [
                    {"id": "backlog", "label": "Backlog", "color": "#90A4AE"},
                    {"id": "ready", "label": "Ready", "color": "#26A69A"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "in_review", "label": "На ревью", "color": "#7E57C2"},
                    {"id": "done", "label": "Done", "color": "#66BB6A"},
                    {"id": "cancelled", "label": "Отменена", "color": "#BDBDBD"},
                ]
            },
            "task:bug": {
                "stages": [
                    {"id": "open", "label": "Open", "color": "#90A4AE"},
                    {"id": "triaged", "label": "Triaged", "color": "#26A69A"},
                    {"id": "in_progress", "label": "Fixing", "color": "#42A5F5"},
                    {"id": "fixed", "label": "Fixed", "color": "#7E57C2"},
                    {"id": "verified", "label": "Verified", "color": "#66BB6A"},
                    {"id": "closed", "label": "Closed", "color": "#BDBDBD"},
                    {"id": "wont_fix", "label": "Won't fix", "color": "#9E9E9E"},
                ]
            },
            "task:spike": {
                "stages": [
                    {"id": "proposed", "label": "Proposed", "color": "#90A4AE"},
                    {"id": "time_boxed", "label": "В работе", "color": "#42A5F5"},
                    {"id": "completed", "label": "Завершён", "color": "#66BB6A"},
                    {"id": "discarded", "label": "Отброшен", "color": "#BDBDBD"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: development (Software engineering / DevOps)
# ----------------------------------------------------------------------


_SEED_DEVELOPMENT = {
    "template_id": "development",
    "name": "Команда разработки",
    "description": (
        "Engineering и DevOps: инциденты с уровнями SEV1–SEV4, "
        "архитектурные решения (ADR), пост-мортемы, runbook'и, фичи и "
        "технический долг. Готовые доски для incident, feature и task."
    ),
    "icon": "code",
    "types": [
        {
            "type_id": "incident",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Инцидент",
            "description": (
                "Сбой или деградация сервиса с понятным impact. Подтип "
                "задачи: ведётся по доске жизненного цикла инцидента."
            ),
            "prompt": (
                "Извлекай инцидент с указанием severity по SEV-шкале, "
                "сервиса и времени начала.\n"
                "Примеры: «SEV2: упал биллинг, началось 12:30, фикс "
                "через час» → incident severity='SEV2', service='биллинг', "
                "started_at=12:30, status='mitigated'.\n"
                "НЕ создавай incident для bug, который не вызвал перебоя "
                "у клиентов — для этого есть bug."
            ),
            "required_fields": {
                "severity": _enum_field(
                    label="Серьёзность (SEV)",
                    description="Уровень инцидента по SLA",
                    values_with_desc=[
                        ("SEV1", "критично: полный простой/массовая потеря данных, эскалация немедленно"),
                        ("SEV2", "серьёзно: ломается ключевой сценарий или большая часть пользователей"),
                        ("SEV3", "ограниченное влияние на часть пользователей"),
                        ("SEV4", "косметика / неудобство, действий по часам не требует"),
                    ],
                ),
            },
            "optional_fields": {
                "service": _string_field(
                    label="Сервис",
                    description="Какой сервис/компонент пострадал.",
                ),
                "started_at": _datetime_field(
                    label="Начало",
                    description="Время первого детектирования инцидента.",
                ),
                "resolved_at": _datetime_field(
                    label="Восстановление",
                    description="Когда инцидент был полностью устранён.",
                ),
                "customer_impact": _text_field(
                    label="Влияние на клиентов",
                    description="Кого затронуло, как долго, какие сценарии не работали.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл инцидента",
                    values_with_desc=[
                        ("detected", "обнаружен, идёт оценка"),
                        ("mitigating", "активная стабилизация"),
                        ("mitigated", "симптомы устранены, корневая причина не закрыта"),
                        ("resolved", "корневая причина устранена"),
                        ("post_mortem", "идёт пост-мортем и action items"),
                        ("closed", "закрыт после пост-мортема"),
                    ],
                ),
            },
            "icon": "error",
            "color": "#D32F2F",
            "is_event": True,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "decision",
            "name": "Архитектурное решение (ADR)",
            "description": (
                "Зафиксированное архитектурное решение по формату ADR: "
                "контекст, альтернативы, выбор, последствия. Якорь для "
                "связанных заметок и реализаций."
            ),
            "prompt": (
                "Извлекай ADR, если в тексте есть выбор между "
                "альтернативами и обоснование.\n"
                "Примеры: «Решено: остаёмся на Postgres вместо Mongo для "
                "контента, причины: транзакции и pgvector» → decision "
                "status='accepted', alternatives='Mongo'.\n"
                "НЕ создавай ADR для рутинных решений уровня одной "
                "задачи."
            ),
            "required_fields": {
                "decision": _text_field(
                    label="Решение",
                    description="Финальный выбор: что именно решили.",
                ),
                "status": _enum_field(
                    label="Статус ADR",
                    description="Жизненный цикл решения",
                    values_with_desc=[
                        ("proposed", "предложено, обсуждается"),
                        ("accepted", "принято и в силе"),
                        ("deprecated", "устарело, не использовать в новом коде"),
                        ("superseded", "заменено другим ADR"),
                    ],
                ),
            },
            "optional_fields": {
                "context": _text_field(
                    label="Контекст",
                    description="Почему решение понадобилось, какие силы действуют.",
                ),
                "alternatives": _text_field(
                    label="Альтернативы",
                    description="Какие варианты рассматривали и почему отвергли.",
                ),
                "consequences": _text_field(
                    label="Последствия",
                    description="Что из решения следует: ограничения, риски, обязательства.",
                ),
                "rfc_link": _string_field(
                    label="Ссылка на RFC",
                    description="Внешняя ссылка на полный текст RFC/ADR-документа.",
                ),
            },
            "icon": "tree-square-dot",
            "color": "#1976D2",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": True,
        },
        {
            "type_id": "post_mortem",
            "name": "Пост-мортем",
            "description": (
                "Разбор инцидента: корневая причина, тайм-лайн, action "
                "items. Привязывается к incident через follows_up."
            ),
            "prompt": (
                "Извлекай пост-мортем по упоминанию разбора инцидента "
                "с RCA и action items.\n"
                "Примеры: «Пост-мортем по падению биллинга: причина — "
                "race condition, action items: тайм-аут и метрика» → "
                "post_mortem root_cause='race condition', action_items=…\n"
                "НЕ создавай post_mortem без явной привязки к инциденту."
            ),
            "required_fields": {},
            "optional_fields": {
                "root_cause": _text_field(
                    label="Корневая причина",
                    description="RCA: что в действительности привело к инциденту.",
                ),
                "timeline": _text_field(
                    label="Тайм-лайн",
                    description="Хронология событий по минутам/часам.",
                ),
                "action_items": _text_field(
                    label="Action items",
                    description="Список конкретных шагов с владельцами и сроками.",
                ),
            },
            "icon": "doc-detail",
            "color": "#5D4037",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": True,
        },
        {
            "type_id": "runbook",
            "name": "Runbook",
            "description": (
                "Операционная инструкция: какой алерт и какие шаги "
                "выполнять. Используется дежурными SRE/on-call."
            ),
            "prompt": (
                "Извлекай runbook, если в тексте есть конкретный "
                "алерт/событие и пошаговая инструкция реагирования.\n"
                "Примеры: «Runbook на алерт `high_lag_kafka`: проверить "
                "consumer lag, рестартнуть consumer» → runbook "
                "triggered_by='high_lag_kafka', steps=…\n"
                "НЕ создавай runbook для общих best practices без "
                "конкретного триггера."
            ),
            "required_fields": {},
            "optional_fields": {
                "triggered_by": _string_field(
                    label="Триггер",
                    description="Алерт или событие, которое запускает runbook.",
                ),
                "steps": _text_field(
                    label="Шаги",
                    description="Пошаговая инструкция реагирования.",
                ),
                "owner_team": _string_field(
                    label="Владеющая команда",
                    description="Кто поддерживает актуальность runbook.",
                ),
            },
            "icon": "checklist",
            "color": "#37474F",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "feature",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Фича",
            "description": (
                "Функциональная единица продукта в жизненном цикле от "
                "плана до релиза или sunset. Подтип задачи."
            ),
            "prompt": (
                "Извлекай новую фичу/функциональность с понятной "
                "пользовательской ценностью.\n"
                "Примеры: «Запускаем экспорт PDF для отчётов» → feature "
                "status='planned'; «Sunset старого онбординга через "
                "месяц» → feature status='sunset'.\n"
                "НЕ создавай feature для багфикса (это bug) и для "
                "технической работы без user-value (это task / "
                "technical_debt)."
            ),
            "required_fields": {},
            "optional_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл фичи",
                    values_with_desc=[
                        ("planned", "запланирована"),
                        ("in_dev", "в разработке"),
                        ("in_qa", "на тестировании"),
                        ("released", "выпущена в прод"),
                        ("sunset", "снимается с поддержки"),
                    ],
                ),
                "target_release": _string_field(
                    label="Целевой релиз",
                    description="Версия релиза, в который планируется фича.",
                ),
            },
            "icon": "chart",
            "color": "#1565C0",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "technical_debt",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Технический долг",
            "description": (
                "Зафиксированный кусок технического долга: что переписать, "
                "оценка стоимости и риска. Подтип задачи."
            ),
            "prompt": (
                "Извлекай явный технический долг с описанием проблемы "
                "и оценкой работы.\n"
                "Примеры: «Старый код миграций тормозит деплой, надо "
                "переписать ~2 недели» → technical_debt "
                "severity='major', cost_estimate_hours=80.\n"
                "НЕ создавай technical_debt для разовых рефакторингов "
                "одной функции — это обычная task."
            ),
            "required_fields": {},
            "optional_fields": {
                "severity": _enum_field(
                    label="Серьёзность",
                    description="Насколько мешает развитию",
                    values_with_desc=[
                        ("minor", "лёгкий неудобный код"),
                        ("major", "тормозит часть фич / онбординг разработчиков"),
                        ("critical", "блокирует развитие целого направления"),
                    ],
                ),
                "cost_estimate_hours": _integer_field(
                    label="Оценка, ч",
                    description="Сколько часов потребуется на устранение.",
                ),
                "risk": _text_field(
                    label="Риск",
                    description="Что произойдёт, если долг не закрыть.",
                ),
            },
            "icon": "error",
            "color": "#6D4C41",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "in_review", "label": "На ревью", "color": "#7E57C2"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:incident": {
                "stages": [
                    {"id": "detected", "label": "Detected", "color": "#EF5350"},
                    {"id": "mitigating", "label": "Mitigating", "color": "#FB8C00"},
                    {"id": "mitigated", "label": "Mitigated", "color": "#FFB74D"},
                    {"id": "resolved", "label": "Resolved", "color": "#66BB6A"},
                    {"id": "post_mortem", "label": "Post-mortem", "color": "#5D4037"},
                    {"id": "closed", "label": "Closed", "color": "#BDBDBD"},
                ]
            },
            "task:feature": {
                "stages": [
                    {"id": "planned", "label": "Planned", "color": "#90A4AE"},
                    {"id": "in_dev", "label": "In Dev", "color": "#42A5F5"},
                    {"id": "in_qa", "label": "In QA", "color": "#7E57C2"},
                    {"id": "released", "label": "Released", "color": "#66BB6A"},
                    {"id": "sunset", "label": "Sunset", "color": "#9E9E9E"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: hr (people ops + recruiting in-house)
# ----------------------------------------------------------------------


_SEED_HR = {
    "template_id": "hr",
    "name": "HR-команда",
    "description": (
        "Внутренний HR: воронка найма (кандидат → офер → сотрудник), "
        "позиции, интервью, performance review и 1-на-1. Готовые доски "
        "для candidate и position."
    ),
    "icon": "user",
    "types": [
        {
            "type_id": "position",
            "name": "Позиция",
            "description": (
                "Открытая вакансия в компании: уровень, департамент, "
                "локация, headcount. Якорь для всех кандидатов и "
                "интервью по этой позиции."
            ),
            "prompt": (
                "Извлекай позицию по упоминанию открытой роли с уровнем "
                "и/или департаментом.\n"
                "Примеры: «Открыли Senior Backend в платформу, 2 хедкаунта» "
                "→ position level='senior', department='Платформа', "
                "headcount=2, status='open'.\n"
                "НЕ создавай позицию для конкретного кандидата (это "
                "candidate) и для общих обсуждений найма."
            ),
            "required_fields": {},
            "optional_fields": {
                "level": _enum_field(
                    label="Уровень",
                    description="Грейд позиции",
                    values_with_desc=[
                        ("intern", "стажёр"),
                        ("junior", "junior, опыт 0–1.5 года"),
                        ("middle", "middle, 1.5–4 года"),
                        ("senior", "senior, 4+ лет"),
                        ("staff", "staff/principal: эксперт сквозного уровня"),
                        ("lead", "тимлид"),
                        ("manager", "менеджер команды/направления"),
                    ],
                ),
                "department": _string_field(
                    label="Департамент",
                    description="Подразделение/команда, для которой позиция.",
                ),
                "location": _string_field(
                    label="Локация",
                    description="Город/страна или `remote`.",
                ),
                "headcount": _integer_field(
                    label="Headcount",
                    description="Сколько человек нужно нанять на эту позицию.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл позиции",
                    values_with_desc=[
                        ("open", "открыта, активный поиск"),
                        ("interviewing", "идут интервью"),
                        ("offered", "сделан офер"),
                        ("filled", "закрыта: кандидат вышел"),
                        ("on_hold", "поставлена на паузу"),
                        ("cancelled", "отменена"),
                    ],
                ),
            },
            "icon": "folder",
            "color": "#5E35B1",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "candidate",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Кандидат",
            "description": (
                "Кандидат на позицию с воронкой sourced→hired. Подтип "
                "задачи: проводится по recruiting funnel."
            ),
            "prompt": (
                "Извлекай нового кандидата с указанием позиции и стадии.\n"
                "Примеры: «Иван прислал резюме на Senior Backend, на "
                "скрининге» → candidate stage='screening', + связь "
                "к position 'Senior Backend'.\n"
                "НЕ создавай candidate для упоминания знакомого «надо "
                "позвать в команду» без действий."
            ),
            "required_fields": {
                "stage": _enum_field(
                    label="Стадия",
                    description="Воронка найма (recruiting funnel)",
                    values_with_desc=[
                        ("sourced", "нашли/получили резюме"),
                        ("screening", "первичный скрининг рекрутёра"),
                        ("interviewing", "идут технические/культурные интервью"),
                        ("offer", "сделан офер, ждём ответ"),
                        ("hired", "вышел в команду"),
                        ("rejected", "отказали мы"),
                        ("withdrawn", "отказался кандидат"),
                    ],
                ),
            },
            "optional_fields": {
                "position_title": _string_field(
                    label="Позиция",
                    description="На какую вакансию рассматривается.",
                ),
                "salary_expectation": _number_field(
                    label="Зарплатные ожидания",
                    description="Ожидаемая компенсация (gross), валюта в отдельном поле.",
                ),
                "currency": _currency_field(),
                "source": _enum_field(
                    label="Источник",
                    description="Откуда пришёл кандидат",
                    values_with_desc=[
                        ("inbound", "сам прислал резюме"),
                        ("agency", "через агентство"),
                        ("referral", "рекомендация сотрудника"),
                        ("event", "с конференции/митапа"),
                        ("active_search", "активный поиск рекрутёра"),
                        ("internal", "внутренний кандидат"),
                    ],
                ),
                "rejection_reason": _string_field(
                    label="Причина отказа",
                    description="Если stage=rejected/withdrawn — кратко почему.",
                ),
            },
            "icon": "user",
            "color": "#8E24AA",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "interview",
            "parent_type_id": MEETING_ENTITY_TYPE_ID,
            "name": "Интервью",
            "description": (
                "Интервью с кандидатом на позицию. Подтип встречи: с "
                "форматом, оценкой и интервьюером."
            ),
            "prompt": (
                "Извлекай состоявшееся интервью с типом и оценкой "
                "результата.\n"
                "Примеры: «System design Ивана — strong yes, "
                "проводила Маша» → interview kind='system_design', "
                "outcome='strong_yes'.\n"
                "НЕ создавай interview для запланированной, но не "
                "состоявшейся встречи."
            ),
            "required_fields": {},
            "optional_fields": {
                "kind": _enum_field(
                    label="Тип интервью",
                    description="Формат интервью",
                    values_with_desc=[
                        ("screen", "скрининг рекрутёра"),
                        ("technical", "техническое интервью"),
                        ("system_design", "system design"),
                        ("behavioral", "поведенческое / опыт"),
                        ("culture", "культурный фит"),
                        ("final", "финальное / с нанимающим менеджером"),
                    ],
                ),
                "outcome": _enum_field(
                    label="Результат",
                    description="Оценка по hire/no-hire шкале",
                    values_with_desc=[
                        ("strong_yes", "strong yes — однозначный хайр"),
                        ("yes", "yes — берём с уверенностью"),
                        ("lean_yes", "lean yes — скорее берём"),
                        ("lean_no", "lean no — скорее не берём"),
                        ("no", "no — не подходит"),
                        ("strong_no", "strong no — не наш кандидат"),
                    ],
                ),
                "interviewer": _string_field(
                    label="Интервьюер",
                    description="Кто проводил интервью.",
                ),
                "notes": _text_field(
                    label="Заметки",
                    description="Сильные/слабые стороны, риски.",
                ),
            },
            "icon": "chat",
            "color": "#00897B",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "offer",
            "name": "Офер",
            "description": (
                "Оформленное предложение работы кандидату со ставкой, "
                "стартовой датой и статусом."
            ),
            "prompt": (
                "Извлекай отправленный кандидату офер с компенсацией и "
                "сроком ответа.\n"
                "Примеры: «Отправили офер Ивану, $120k + опционы, "
                "выход 1 мая» → offer salary_amount=120000, "
                "currency='USD', start_date=2024-05-01, status='sent'.\n"
                "НЕ создавай offer для устных намёков без оформленного "
                "предложения."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл офера",
                    values_with_desc=[
                        ("drafted", "черновик, ещё не отправили"),
                        ("sent", "отправлен кандидату"),
                        ("accepted", "принят"),
                        ("declined", "отклонён кандидатом"),
                        ("expired", "срок ответа истёк"),
                    ],
                ),
            },
            "optional_fields": {
                "salary_amount": _number_field(
                    label="Зарплата",
                    description="Сумма компенсации (gross/year).",
                ),
                "currency": _currency_field(),
                "equity_pct": _number_field(
                    label="Доля опционов, %",
                    description="Опционы/equity в процентах.",
                ),
                "bonus": _string_field(
                    label="Бонусы",
                    description="Сигнинг-бонус, релокация и прочие условия.",
                ),
                "start_date": _date_field(
                    label="Дата выхода",
                    description="Плановая дата старта работы.",
                ),
            },
            "icon": "doc-detail",
            "color": "#7E57C2",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "employee",
            "name": "Сотрудник",
            "description": (
                "Нанятый сотрудник компании. Используется HR для "
                "performance review, 1-на-1 и кадровых заметок. "
                "Не путать с `member` (учётная запись на платформе)."
            ),
            "prompt": (
                "Извлекай сотрудника по упоминанию активного работника "
                "со штатной должностью.\n"
                "Примеры: «У Маши 2 года в команде, переходит на "
                "senior» → employee level='senior', start_date=… (если "
                "указана).\n"
                "НЕ создавай employee для кандидатов до hire и для "
                "внешних подрядчиков."
            ),
            "required_fields": {},
            "optional_fields": {
                "level": _string_field(
                    label="Уровень",
                    description="Грейд сотрудника (junior/middle/senior и т.п.).",
                ),
                "department": _string_field(
                    label="Департамент",
                    description="Подразделение, в котором работает сотрудник.",
                ),
                "start_date": _date_field(
                    label="Дата выхода",
                    description="Когда сотрудник вышел в компанию.",
                ),
                "manager": _string_field(
                    label="Руководитель",
                    description="Имя непосредственного руководителя.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Состояние трудовых отношений",
                    values_with_desc=[
                        ("active", "активный сотрудник"),
                        ("on_leave", "в долгом отпуске / декрете"),
                        ("notice", "на отработке после увольнения"),
                        ("offboarded", "уволен"),
                    ],
                ),
            },
            "icon": "user-shield",
            "color": "#3949AB",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "performance_review",
            "name": "Performance review",
            "description": (
                "Обзор производительности сотрудника за период с "
                "оценкой и обратной связью."
            ),
            "prompt": (
                "Извлекай состоявшееся ревью с периодом, оценкой и "
                "ключевыми пунктами обратной связи.\n"
                "Примеры: «Перфоманс Маши за H1: exceeds expectations, "
                "продлеваем кост-плюс» → performance_review "
                "period='H1', rating='exceeds'.\n"
                "НЕ создавай performance_review для разового фидбека — "
                "это обычная note."
            ),
            "required_fields": {},
            "optional_fields": {
                "period": _string_field(
                    label="Период",
                    description="Какой период покрывает ревью (`H1 2024`, `Q3` и т.п.).",
                ),
                "rating": _enum_field(
                    label="Оценка",
                    description="Итоговый рейтинг по шкале performance",
                    values_with_desc=[
                        ("below", "ниже ожиданий"),
                        ("meets", "соответствует ожиданиям"),
                        ("exceeds", "превышает ожидания"),
                        ("outstanding", "выдающийся результат"),
                    ],
                ),
                "strengths": _text_field(
                    label="Сильные стороны",
                    description="Что у сотрудника получается лучше всего.",
                ),
                "growth_areas": _text_field(
                    label="Точки роста",
                    description="Что развивать в следующий период.",
                ),
            },
            "icon": "chart",
            "color": "#00897B",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "one_on_one",
            "parent_type_id": MEETING_ENTITY_TYPE_ID,
            "name": "1-на-1",
            "description": (
                "Встреча 1-на-1 руководитель ↔ подчинённый: точки роста, "
                "блокеры, фидбек. Подтип встречи."
            ),
            "prompt": (
                "Извлекай состоявшийся 1-на-1 с участниками и "
                "результатами разговора.\n"
                "Примеры: «1-на-1 с Машей: обсудили growth-план, "
                "блокер по доступам — снимаем» → one_on_one с "
                "decisions/next_actions.\n"
                "НЕ создавай one_on_one для общего совещания (это "
                "meeting)."
            ),
            "required_fields": {},
            "optional_fields": {
                "topics": _text_field(
                    label="Темы",
                    description="Что обсуждали на 1-на-1.",
                ),
                "blockers": _text_field(
                    label="Блокеры",
                    description="Что мешает сотруднику работать; что нужно от руководителя.",
                ),
                "growth_plan": _text_field(
                    label="План развития",
                    description="Цели роста и шаги до следующего 1-на-1.",
                ),
            },
            "icon": "users",
            "color": "#26A69A",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:candidate": {
                "stages": [
                    {"id": "sourced", "label": "Sourced", "color": "#90A4AE"},
                    {"id": "screening", "label": "Screening", "color": "#42A5F5"},
                    {"id": "interviewing", "label": "Interviewing", "color": "#7E57C2"},
                    {"id": "offer", "label": "Offer", "color": "#FB8C00"},
                    {"id": "hired", "label": "Hired", "color": "#66BB6A"},
                    {"id": "rejected", "label": "Rejected", "color": "#BDBDBD"},
                    {"id": "withdrawn", "label": "Withdrawn", "color": "#9E9E9E"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: marketing
# ----------------------------------------------------------------------


_SEED_MARKETING = {
    "template_id": "marketing",
    "name": "Маркетинг",
    "description": (
        "Маркетинговая команда: кампании, каналы, контент, аудитории и "
        "бренд-ассеты. Готовые доски для жизненного цикла кампании и "
        "production-pipeline контента."
    ),
    "icon": "chart",
    "types": [
        {
            "type_id": "campaign",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Кампания",
            "description": (
                "Маркетинговая кампания с целью, бюджетом, каналами и "
                "сроком. Подтип задачи: ведётся по доске жизненного "
                "цикла."
            ),
            "prompt": (
                "Извлекай кампанию по упоминанию названия, цели и сроков.\n"
                "Примеры: «Запускаем performance-кампанию Q3 на $20k, "
                "до конца сентября» → campaign budget=20000, "
                "currency='USD', objective='generate Q3 leads', "
                "status='running'.\n"
                "НЕ создавай кампанию для разовой публикации в соцсетях "
                "— для этого есть content."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл кампании",
                    values_with_desc=[
                        ("planned", "запланирована"),
                        ("creative", "идёт продакшн креатива"),
                        ("running", "запущена"),
                        ("paused", "поставлена на паузу"),
                        ("completed", "завершена, идёт анализ"),
                        ("cancelled", "отменена"),
                    ],
                ),
            },
            "optional_fields": {
                "objective": _text_field(
                    label="Цель",
                    description="Бизнес-цель кампании (KPI, generate leads, brand awareness…).",
                ),
                "budget": _number_field(
                    label="Бюджет",
                    description="Общий бюджет кампании.",
                ),
                "currency": _currency_field(),
                "start_date": _date_field(label="Старт", description="Дата старта кампании."),
                "end_date": _date_field(
                    label="Завершение",
                    description="Плановая дата окончания кампании.",
                ),
                "kpi_target": _string_field(
                    label="Целевой KPI",
                    description="Числовой ориентир: leads, MQLs, revenue, ROAS и т.п.",
                ),
            },
            "icon": "chart-multifunction",
            "color": "#D81B60",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "channel",
            "name": "Канал",
            "description": (
                "Канал коммуникации/трафика: email-рассылка, соцсеть, "
                "SEO, paid, partner и т.п. Используется как контекст для "
                "кампаний и контента."
            ),
            "prompt": (
                "Извлекай канал по упоминанию конкретного канала и его "
                "вида.\n"
                "Примеры: «Запустили в Telegram Ads» → channel kind='paid', "
                "name='Telegram Ads'; «Email-рассылка для апрельской "
                "когорты» → channel kind='email', name='April newsletter'.\n"
                "НЕ создавай channel для одной публикации — это content."
            ),
            "required_fields": {},
            "optional_fields": {
                "kind": _enum_field(
                    label="Вид канала",
                    description="Тип маркетингового канала",
                    values_with_desc=[
                        ("email", "email-маркетинг"),
                        ("social", "социальные сети (organic)"),
                        ("seo", "SEO / органический поиск"),
                        ("paid", "paid acquisition (контекст, programmatic)"),
                        ("content", "контент-маркетинг (блог, гайды)"),
                        ("event", "офлайн/онлайн ивенты"),
                        ("partner", "партнёрский / co-marketing"),
                        ("influencer", "инфлюенсеры / лидеры мнений"),
                        ("pr", "PR / медиа-публикации"),
                    ],
                ),
                "owner_role": _string_field(
                    label="Владелец канала",
                    description="Кто ведёт этот канал на стороне команды.",
                ),
            },
            "icon": "circular-connection",
            "color": "#AD1457",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "content",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Контент",
            "description": (
                "Единица контента в продакшне: пост, статья, видео, "
                "лендинг, кейс. Подтип задачи: ведётся по contentboard."
            ),
            "prompt": (
                "Извлекай контент по упоминанию формата и темы.\n"
                "Примеры: «Готовим лонгрид про миграцию на Postgres» → "
                "content format='article', status='in_review'; "
                "«Пост в LinkedIn анонс релиза» → content "
                "format='social_post', status='published'.\n"
                "НЕ создавай content для целой кампании — для этого есть "
                "campaign."
            ),
            "required_fields": {},
            "optional_fields": {
                "format": _enum_field(
                    label="Формат",
                    description="Формат контентной единицы",
                    values_with_desc=[
                        ("article", "статья / блог / лонгрид"),
                        ("social_post", "пост в соцсети"),
                        ("video", "видео / shorts"),
                        ("podcast", "подкаст / эпизод"),
                        ("landing", "лендинг / страница"),
                        ("email", "письмо / рассылка"),
                        ("case_study", "кейс-стади"),
                        ("whitepaper", "white-paper / гайд"),
                        ("infographic", "инфографика"),
                    ],
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Стадия production",
                    values_with_desc=[
                        ("idea", "идея / в бэклоге"),
                        ("drafting", "пишется / монтируется"),
                        ("in_review", "на ревью / редактуре"),
                        ("approved", "согласован, готов к публикации"),
                        ("published", "опубликован"),
                        ("archived", "снят с публикации"),
                    ],
                ),
                "publish_date": _date_field(
                    label="Дата публикации",
                    description="Когда планируется или произошла публикация.",
                ),
                "url": _string_field(
                    label="URL",
                    description="Ссылка на опубликованный материал.",
                ),
            },
            "icon": "doc-detail",
            "color": "#EC407A",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "audience_segment",
            "name": "Аудитория",
            "description": (
                "Сегмент целевой аудитории: by ICP, by behavior, by "
                "lifecycle. Якорь для кампаний и контента."
            ),
            "prompt": (
                "Извлекай сегмент по упоминанию конкретной аудитории "
                "(ICP, отрасль, размер компании, lifecycle).\n"
                "Примеры: «Кампания для SMB-команд из IT в РФ» → "
                "audience_segment с описанием.\n"
                "НЕ создавай сегмент для одного клиента (это account / "
                "contact)."
            ),
            "required_fields": {},
            "optional_fields": {
                "criteria": _text_field(
                    label="Критерии",
                    description="По каким признакам выделен сегмент.",
                ),
                "size_estimate": _integer_field(
                    label="Оценка размера",
                    description="Сколько примерно потенциальных клиентов в сегменте.",
                ),
                "lifecycle_stage": _enum_field(
                    label="Lifecycle",
                    description="На каком этапе цикла маркетинга находятся",
                    values_with_desc=[
                        ("awareness", "знакомство с проблемой/брендом"),
                        ("consideration", "рассматривают варианты решения"),
                        ("decision", "выбирают конкретного поставщика"),
                        ("retention", "уже клиенты, удержание"),
                        ("advocacy", "адвокаты бренда / евангелисты"),
                    ],
                ),
            },
            "icon": "users",
            "color": "#F06292",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "lead_source",
            "name": "Источник лидов",
            "description": (
                "Конкретный источник входящих лидов: посадочная "
                "страница, форма, конференция. Используется для атрибуции."
            ),
            "prompt": (
                "Извлекай источник лидов по упоминанию атрибуционного "
                "канала генерации.\n"
                "Примеры: «С формы блога пришло 12 лидов» → lead_source "
                "kind='blog_form', metric_value=12.\n"
                "НЕ путай с channel — channel шире (паблишинг + ивенты + "
                "медиа); lead_source — точка съёма контактов."
            ),
            "required_fields": {},
            "optional_fields": {
                "kind": _string_field(
                    label="Вид источника",
                    description="Конкретный источник: form, landing, webinar, conf-list…",
                ),
                "tracking_id": _string_field(
                    label="UTM / tracking",
                    description="UTM-метка или другой идентификатор атрибуции.",
                ),
            },
            "icon": "target-lock",
            "color": "#C2185B",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "asset",
            "name": "Бренд-ассет",
            "description": (
                "Многоразовый материал для маркетинга: логотип, "
                "шаблон письма, баннер, видео-заставка."
            ),
            "prompt": (
                "Извлекай переиспользуемый бренд-ассет по упоминанию "
                "файла/шаблона/визуала.\n"
                "Примеры: «Обновили шаблон email-подписи» → asset "
                "kind='template', name='Email signature'.\n"
                "НЕ создавай asset для разовой публикации (это content)."
            ),
            "required_fields": {},
            "optional_fields": {
                "kind": _enum_field(
                    label="Вид ассета",
                    description="Тип бренд-ассета",
                    values_with_desc=[
                        ("logo", "логотип"),
                        ("template", "шаблон письма / документа"),
                        ("banner", "баннер / hero-визуал"),
                        ("video", "видео / mascot"),
                        ("photo", "фото / стоковый материал"),
                        ("guideline", "брендбук / guideline"),
                    ],
                ),
                "url": _string_field(
                    label="URL / расположение",
                    description="Ссылка на файл в DAM или облачном хранилище.",
                ),
            },
            "icon": "doc-detail",
            "color": "#F48FB1",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:campaign": {
                "stages": [
                    {"id": "planned", "label": "Planned", "color": "#90A4AE"},
                    {"id": "creative", "label": "Creative", "color": "#7E57C2"},
                    {"id": "running", "label": "Running", "color": "#42A5F5"},
                    {"id": "paused", "label": "Paused", "color": "#FFB74D"},
                    {"id": "completed", "label": "Completed", "color": "#66BB6A"},
                    {"id": "cancelled", "label": "Cancelled", "color": "#BDBDBD"},
                ]
            },
            "task:content": {
                "stages": [
                    {"id": "idea", "label": "Idea", "color": "#90A4AE"},
                    {"id": "drafting", "label": "Drafting", "color": "#42A5F5"},
                    {"id": "in_review", "label": "In Review", "color": "#7E57C2"},
                    {"id": "approved", "label": "Approved", "color": "#26A69A"},
                    {"id": "published", "label": "Published", "color": "#66BB6A"},
                    {"id": "archived", "label": "Archived", "color": "#BDBDBD"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: support
# ----------------------------------------------------------------------


_SEED_SUPPORT = {
    "template_id": "support",
    "name": "Клиентская поддержка",
    "description": (
        "Customer support: тикеты с SLA, знание-база, инциденты "
        "видимые клиенту, заметки о клиентах. Готовые доски для "
        "ticket workflow и редакторской KB."
    ),
    "icon": "chat",
    "types": [
        {
            "type_id": "ticket",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Тикет",
            "description": (
                "Обращение клиента в поддержку с категорией, severity и "
                "SLA. Подтип задачи: ведётся по ticket workflow."
            ),
            "prompt": (
                "Извлекай тикет по упоминанию обращения клиента с темой и "
                "приоритетом.\n"
                "Примеры: «Acme не может залогиниться, severity high, "
                "SLA 2 часа» → ticket severity='high', "
                "category='auth', sla_minutes=120, status='open'.\n"
                "НЕ создавай ticket для внутреннего бага без обращения "
                "клиента — это bug."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Стадия обработки тикета",
                    values_with_desc=[
                        ("open", "новый, не взят в работу"),
                        ("in_progress", "в работе у агента"),
                        ("waiting_customer", "ждём ответа клиента"),
                        ("waiting_internal", "ждём ответа внутренней команды"),
                        ("resolved", "решён, отправлен ответ клиенту"),
                        ("closed", "закрыт"),
                        ("escalated", "эскалирован 2-й/3-й линии или PM"),
                    ],
                ),
            },
            "optional_fields": {
                "severity": _enum_field(
                    label="Severity",
                    description="Влияние проблемы на клиента",
                    values_with_desc=[
                        ("urgent", "критично: продакшн клиента не работает"),
                        ("high", "серьёзно: ключевой сценарий нарушен"),
                        ("normal", "стандартный запрос/проблема"),
                        ("low", "вопрос/уточнение, не блокирует"),
                    ],
                ),
                "category": _enum_field(
                    label="Категория",
                    description="Тематика обращения",
                    values_with_desc=[
                        ("bug", "баг в продукте"),
                        ("question", "вопрос по продукту"),
                        ("billing", "биллинг / тарификация"),
                        ("auth", "вход / аккаунты"),
                        ("integration", "интеграции / API"),
                        ("feature_request", "запрос новой фичи"),
                        ("other", "другое"),
                    ],
                ),
                "sla_minutes": _integer_field(
                    label="SLA, мин",
                    description="Целевое время ответа/решения по SLA в минутах.",
                ),
                "channel": _enum_field(
                    label="Канал обращения",
                    description="Откуда пришло обращение",
                    values_with_desc=[
                        ("email", "email"),
                        ("chat", "чат на сайте / в продукте"),
                        ("phone", "телефонный звонок"),
                        ("portal", "тикет-портал"),
                        ("social", "соцсети / публичные каналы"),
                    ],
                ),
                "first_response_at": _datetime_field(
                    label="Первый ответ",
                    description="Когда агент впервые ответил клиенту.",
                ),
            },
            "icon": "chat",
            "color": "#039BE5",
            "is_event": True,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "incident",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Инцидент (видимый клиентам)",
            "description": (
                "Массовый инцидент с публичным impact: страница статуса, "
                "коммуникация клиентам. Подтип задачи."
            ),
            "prompt": (
                "Извлекай инцидент с публичным impact: затронуты "
                "несколько клиентов, есть статус-page или массовая "
                "коммуникация.\n"
                "Примеры: «Деградация API 14:00–15:30, выложили на "
                "статус-page» → incident severity='SEV2', "
                "started_at='14:00', resolved_at='15:30'.\n"
                "НЕ путай с ticket: ticket — обращение одного клиента."
            ),
            "required_fields": {
                "severity": _enum_field(
                    label="Severity",
                    description="Уровень публичного инцидента",
                    values_with_desc=[
                        ("SEV1", "полный простой / массовая потеря данных"),
                        ("SEV2", "ключевой сценарий не работает у большинства"),
                        ("SEV3", "ограниченное влияние на часть клиентов"),
                        ("SEV4", "косметика, можно отложить"),
                    ],
                ),
            },
            "optional_fields": {
                "started_at": _datetime_field(
                    label="Начало",
                    description="Когда инцидент начал затрагивать клиентов.",
                ),
                "resolved_at": _datetime_field(
                    label="Восстановление",
                    description="Когда сервис восстановлен.",
                ),
                "affected_customers": _integer_field(
                    label="Затронуто клиентов",
                    description="Оценка количества пострадавших клиентов.",
                ),
                "status_page_url": _string_field(
                    label="Status page",
                    description="Ссылка на публичную страницу статуса.",
                ),
            },
            "icon": "error",
            "color": "#E64A19",
            "is_event": True,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "customer",
            "name": "Клиент",
            "description": (
                "Клиент-аккаунт со стороны поддержки: сегмент, тариф, "
                "история обращений. Контейнер для всех тикетов клиента."
            ),
            "prompt": (
                "Извлекай клиента-аккаунт по упоминанию названия "
                "компании-клиента или его сегмента.\n"
                "Примеры: «Acme на тарифе Enterprise, MRR $5k» → "
                "customer tier='enterprise'.\n"
                "НЕ создавай отдельную customer-сущность для разового "
                "вопроса от частного лица."
            ),
            "required_fields": {},
            "optional_fields": {
                "tier": _enum_field(
                    label="Тариф/сегмент",
                    description="Тарифный план или сегмент клиента",
                    values_with_desc=[
                        ("free", "бесплатный план"),
                        ("starter", "стартовый тариф"),
                        ("pro", "профессиональный"),
                        ("business", "бизнес-уровень"),
                        ("enterprise", "энтерпрайз / индивидуальный контракт"),
                    ],
                ),
                "csm": _string_field(
                    label="CSM",
                    description="Имя customer success менеджера.",
                ),
                "health": _enum_field(
                    label="Здоровье аккаунта",
                    description="Сводный сигнал по retention",
                    values_with_desc=_HEALTH_VALUES,
                ),
            },
            "icon": "building",
            "color": "#0277BD",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "knowledge_article",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Статья KB",
            "description": (
                "Статья базы знаний: how-to, troubleshooting, FAQ. "
                "Подтип задачи: ведётся по редакторскому workflow."
            ),
            "prompt": (
                "Извлекай статью KB по упоминанию материала справки/"
                "документации.\n"
                "Примеры: «Написал статью про настройку SSO» → "
                "knowledge_article category='auth', status='draft'.\n"
                "НЕ создавай KB-статью для одного ответа клиенту — это "
                "ticket с reply."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл статьи",
                    values_with_desc=[
                        ("draft", "черновик"),
                        ("in_review", "на ревью у редактора/SME"),
                        ("published", "опубликована"),
                        ("outdated", "устарела, нужна актуализация"),
                        ("archived", "снята с публикации"),
                    ],
                ),
            },
            "optional_fields": {
                "category": _string_field(
                    label="Категория",
                    description="Раздел KB: getting started, billing, integrations…",
                ),
                "url": _string_field(
                    label="URL",
                    description="Публичная ссылка на статью.",
                ),
                "author": _string_field(
                    label="Автор",
                    description="Кто написал/поддерживает статью.",
                ),
            },
            "icon": "doc-detail",
            "color": "#0288D1",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "faq",
            "name": "FAQ",
            "description": (
                "Часто задаваемый вопрос с готовым ответом. Используется "
                "поддержкой как макрос/сниппет."
            ),
            "prompt": (
                "Извлекай FAQ по упоминанию повторяющегося вопроса с "
                "ответом.\n"
                "Примеры: «Часто спрашивают про лимиты API — добавил FAQ» "
                "→ faq question='Какие лимиты API?', answer=…\n"
                "НЕ создавай FAQ для конкретного тикета — это reply на "
                "ticket."
            ),
            "required_fields": {},
            "optional_fields": {
                "question": _text_field(
                    label="Вопрос",
                    description="Формулировка вопроса как его задают клиенты.",
                ),
                "answer": _text_field(
                    label="Ответ",
                    description="Канонический ответ для использования агентами.",
                ),
                "category": _string_field(
                    label="Категория",
                    description="Раздел FAQ.",
                ),
            },
            "icon": "chat",
            "color": "#01579B",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:ticket": {
                "stages": [
                    {"id": "open", "label": "Open", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "In progress", "color": "#42A5F5"},
                    {"id": "waiting_customer", "label": "Waiting on customer", "color": "#FFB74D"},
                    {"id": "waiting_internal", "label": "Waiting on team", "color": "#FFA726"},
                    {"id": "resolved", "label": "Resolved", "color": "#66BB6A"},
                    {"id": "closed", "label": "Closed", "color": "#BDBDBD"},
                    {"id": "escalated", "label": "Escalated", "color": "#EF5350"},
                ]
            },
            "task:incident": {
                "stages": [
                    {"id": "detected", "label": "Detected", "color": "#EF5350"},
                    {"id": "investigating", "label": "Investigating", "color": "#FB8C00"},
                    {"id": "mitigating", "label": "Mitigating", "color": "#FFB74D"},
                    {"id": "resolved", "label": "Resolved", "color": "#66BB6A"},
                    {"id": "closed", "label": "Closed", "color": "#BDBDBD"},
                ]
            },
            "task:knowledge_article": {
                "stages": [
                    {"id": "draft", "label": "Draft", "color": "#90A4AE"},
                    {"id": "in_review", "label": "Review", "color": "#7E57C2"},
                    {"id": "published", "label": "Published", "color": "#66BB6A"},
                    {"id": "outdated", "label": "Outdated", "color": "#FFB74D"},
                    {"id": "archived", "label": "Archived", "color": "#BDBDBD"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: product_management
# ----------------------------------------------------------------------


_SEED_PRODUCT = {
    "template_id": "product_management",
    "name": "Продукт-менеджмент",
    "description": (
        "Discovery → delivery → impact: инициативы, opportunity по Cagan, "
        "гипотезы, эксперименты, фичи и OKR. Готовые доски для discovery, "
        "delivery, OKR-цикла."
    ),
    "icon": "chart-multifunction",
    "types": [
        {
            "type_id": "initiative",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Инициатива",
            "description": (
                "Стратегическая инициатива продукта (выше эпика): связка "
                "целевого результата и нескольких opportunities. Подтип "
                "задачи."
            ),
            "prompt": (
                "Извлекай инициативу по стратегическому фокусу с целью "
                "и горизонтом.\n"
                "Примеры: «Инициатива H2: ускорить онбординг до 2 дней» → "
                "initiative objective='ускорить онбординг до 2 дней', "
                "horizon='H2'.\n"
                "НЕ создавай initiative для разовой фичи (это feature)."
            ),
            "required_fields": {},
            "optional_fields": {
                "objective": _text_field(
                    label="Цель",
                    description="Выходной бизнес-результат инициативы.",
                ),
                "horizon": _string_field(
                    label="Горизонт",
                    description="Период: Q3 2024, H1 2025 и т.п.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл инициативы",
                    values_with_desc=[
                        ("planned", "запланирована"),
                        ("discovery", "идёт discovery"),
                        ("delivery", "идёт delivery"),
                        ("measuring", "идёт измерение impact"),
                        ("done", "завершена"),
                        ("cancelled", "отменена"),
                    ],
                ),
            },
            "icon": "layers",
            "color": "#5E35B1",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "opportunity",
            "name": "Opportunity",
            "description": (
                "Pain или потребность пользователя по Marty Cagan: "
                "формулировка проблемы, не решения. Якорь для гипотез "
                "и экспериментов."
            ),
            "prompt": (
                "Извлекай opportunity как пользовательскую боль/"
                "потребность, БЕЗ привязки к конкретному решению.\n"
                "Примеры: «Пользователи не понимают, как пригласить "
                "коллегу» → opportunity, evidence='3 саппорт-тикета "
                "за неделю'.\n"
                "НЕ формулируй opportunity как решение («Сделать кнопку "
                "invite»)."
            ),
            "required_fields": {},
            "optional_fields": {
                "evidence": _text_field(
                    label="Доказательства",
                    description="Какие данные/наблюдения подтверждают opportunity.",
                ),
                "size_score": _enum_field(
                    label="Размер",
                    description="Оценка размера opportunity",
                    values_with_desc=[
                        ("small", "малая: единичная боль"),
                        ("medium", "средняя: ощутима для сегмента"),
                        ("large", "большая: ключевая для retention/acquisition"),
                    ],
                ),
                "confidence_score": _enum_field(
                    label="Уверенность",
                    description="Насколько уверены в существовании проблемы",
                    values_with_desc=[
                        ("low", "по 1–2 наблюдениям"),
                        ("medium", "из нескольких источников"),
                        ("high", "подтверждена данными и исследованиями"),
                    ],
                ),
            },
            "icon": "target-lock",
            "color": "#3949AB",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "hypothesis",
            "name": "Гипотеза",
            "description": (
                "Гипотеза вида «если сделаем X, то получим Y, потому "
                "что Z». Связана с opportunity, проверяется experiment'ом."
            ),
            "prompt": (
                "Извлекай гипотезу с явной структурой условие → следствие.\n"
                "Примеры: «Если добавим onboarding-tour, retention "
                "вырастет на 5%, потому что пользователи поймут "
                "ключевые сценарии» → hypothesis с этим текстом.\n"
                "НЕ путай гипотезу с задачей — гипотеза не "
                "запланированное действие, а проверяемое утверждение."
            ),
            "required_fields": {},
            "optional_fields": {
                "statement": _text_field(
                    label="Формулировка",
                    description="Полная формулировка гипотезы (если/то/потому что).",
                ),
                "expected_metric": _string_field(
                    label="Ожидаемый эффект",
                    description="Какую метрику и как изменит гипотеза.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Состояние гипотезы",
                    values_with_desc=[
                        ("proposed", "сформулирована, ждёт эксперимента"),
                        ("testing", "идёт эксперимент"),
                        ("validated", "подтверждена"),
                        ("invalidated", "опровергнута"),
                    ],
                ),
            },
            "icon": "doc-detail",
            "color": "#1E88E5",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "experiment",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Эксперимент",
            "description": (
                "Конкретный эксперимент для проверки гипотезы: метод, "
                "выборка, результат. Подтип задачи."
            ),
            "prompt": (
                "Извлекай эксперимент по упоминанию метода проверки и "
                "выборки.\n"
                "Примеры: «Запускаем A/B новой формы для 10% пользователей "
                "на 2 недели» → experiment method='ab_test', "
                "status='running'.\n"
                "НЕ создавай experiment для разовой презентации идеи."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл эксперимента",
                    values_with_desc=[
                        ("planned", "запланирован"),
                        ("running", "запущен"),
                        ("completed", "завершён, идёт анализ"),
                        ("inconclusive", "результаты неоднозначны"),
                        ("succeeded", "гипотеза подтвердилась"),
                        ("failed", "гипотеза опровергнута"),
                    ],
                ),
            },
            "optional_fields": {
                "method": _enum_field(
                    label="Метод",
                    description="Способ проверки гипотезы",
                    values_with_desc=[
                        ("ab_test", "A/B-тест"),
                        ("interview", "интервью с пользователями"),
                        ("usability", "юзабилити-тестирование"),
                        ("survey", "опрос"),
                        ("concierge", "concierge / wizard of oz"),
                        ("prototype", "прототип / мокап"),
                    ],
                ),
                "metric": _string_field(
                    label="Метрика",
                    description="Какую метрику меряем.",
                ),
                "sample_size": _integer_field(
                    label="Размер выборки",
                    description="Сколько пользователей участвует.",
                ),
                "result": _text_field(
                    label="Результат",
                    description="Краткие выводы и числа после завершения.",
                ),
            },
            "icon": "chart",
            "color": "#1565C0",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "feature",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Фича",
            "description": (
                "Функция продукта в delivery с пользовательской "
                "ценностью и метрикой успеха. Подтип задачи."
            ),
            "prompt": (
                "Извлекай фичу с пользовательской ценностью и хотя бы "
                "одной метрикой успеха.\n"
                "Примеры: «Запускаем экспорт в Excel, цель — 30% "
                "пользователей за месяц» → feature, success_metric='30% "
                "пользователей за месяц'.\n"
                "НЕ создавай feature для технической работы без "
                "пользовательской ценности."
            ),
            "required_fields": {},
            "optional_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл фичи",
                    values_with_desc=[
                        ("ideation", "идея / описание"),
                        ("discovery", "идёт discovery"),
                        ("ready", "готова к разработке"),
                        ("in_dev", "в разработке"),
                        ("in_qa", "на тестировании"),
                        ("released", "выпущена"),
                        ("measuring", "идёт измерение impact"),
                        ("sunset", "снимается с поддержки"),
                    ],
                ),
                "success_metric": _string_field(
                    label="Метрика успеха",
                    description="Какая метрика и как должна измениться.",
                ),
                "target_release": _string_field(
                    label="Целевой релиз",
                    description="Версия/итерация выпуска.",
                ),
            },
            "icon": "chart-multifunction",
            "color": "#0277BD",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "okr_objective",
            "name": "OKR Objective",
            "description": (
                "Цель в формате OKR на период (квартал/полугодие). "
                "Контейнер для key_result."
            ),
            "prompt": (
                "Извлекай objective с явным владельцем и периодом.\n"
                "Примеры: «Q3 Objective: ускорить онбординг» → "
                "okr_objective period='Q3 2024', owner_role='PM team'.\n"
                "НЕ создавай objective без периода или для разовой "
                "задачи."
            ),
            "required_fields": {
                "period": _string_field(
                    label="Период",
                    description="Q1/Q2/Q3/Q4/H1/H2 и год.",
                ),
            },
            "optional_fields": {
                "owner_role": _string_field(
                    label="Владелец",
                    description="Команда или роль, которая отвечает за objective.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Состояние objective",
                    values_with_desc=[
                        ("planned", "запланирован, скоро стартует"),
                        ("active", "идёт работа над OKR"),
                        ("at_risk", "под угрозой невыполнения"),
                        ("achieved", "достигнут"),
                        ("missed", "не достигнут"),
                    ],
                ),
            },
            "icon": "target-lock",
            "color": "#283593",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "key_result",
            "name": "Key Result",
            "description": (
                "Измеримый key result для objective: метрика, целевое "
                "значение, текущий прогресс."
            ),
            "prompt": (
                "Извлекай KR как метрику с целевым значением и единицей.\n"
                "Примеры: «KR1: TTV сократить с 5 до 2 дней» → key_result "
                "target=2, current=5, unit='дни'.\n"
                "НЕ создавай KR без числового таргета (это уже не KR)."
            ),
            "required_fields": {},
            "optional_fields": {
                "target": _number_field(
                    label="Цель",
                    description="Целевое значение метрики на конец периода.",
                ),
                "current": _number_field(
                    label="Текущее",
                    description="Текущее значение метрики.",
                ),
                "unit": _string_field(
                    label="Единица",
                    description="Единица измерения: %, дни, $/MAU и т.п.",
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Состояние KR",
                    values_with_desc=[
                        ("on_track", "идёт по плану"),
                        ("at_risk", "под угрозой"),
                        ("off_track", "сильно отстаёт"),
                        ("achieved", "достигнут"),
                    ],
                ),
            },
            "icon": "chart",
            "color": "#1A237E",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:initiative": {
                "stages": [
                    {"id": "planned", "label": "Planned", "color": "#90A4AE"},
                    {"id": "discovery", "label": "Discovery", "color": "#7E57C2"},
                    {"id": "delivery", "label": "Delivery", "color": "#42A5F5"},
                    {"id": "measuring", "label": "Measuring", "color": "#FFB74D"},
                    {"id": "done", "label": "Done", "color": "#66BB6A"},
                    {"id": "cancelled", "label": "Cancelled", "color": "#BDBDBD"},
                ]
            },
            "task:experiment": {
                "stages": [
                    {"id": "planned", "label": "Planned", "color": "#90A4AE"},
                    {"id": "running", "label": "Running", "color": "#42A5F5"},
                    {"id": "completed", "label": "Completed", "color": "#7E57C2"},
                    {"id": "succeeded", "label": "Succeeded", "color": "#66BB6A"},
                    {"id": "failed", "label": "Failed", "color": "#EF5350"},
                    {"id": "inconclusive", "label": "Inconclusive", "color": "#BDBDBD"},
                ]
            },
            "task:feature": {
                "stages": [
                    {"id": "ideation", "label": "Ideation", "color": "#90A4AE"},
                    {"id": "discovery", "label": "Discovery", "color": "#7E57C2"},
                    {"id": "ready", "label": "Ready", "color": "#26A69A"},
                    {"id": "in_dev", "label": "In Dev", "color": "#42A5F5"},
                    {"id": "in_qa", "label": "In QA", "color": "#7E57C2"},
                    {"id": "released", "label": "Released", "color": "#66BB6A"},
                    {"id": "measuring", "label": "Measuring", "color": "#FFB74D"},
                    {"id": "sunset", "label": "Sunset", "color": "#9E9E9E"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: recruiting (агентский / RPO)
# ----------------------------------------------------------------------


_SEED_RECRUITING = {
    "template_id": "recruiting",
    "name": "Кадровое агентство",
    "description": (
        "Агентский рекрутинг и RPO: кандидаты, позиции, клиент-компании, "
        "submissions, placements. Отдельный от внутреннего HR пакет — "
        "рассчитан на работу с несколькими клиентами одновременно."
    ),
    "icon": "user",
    "types": [
        {
            "type_id": "client_company",
            "name": "Клиент-компания",
            "description": (
                "Заказчик, которому агентство ищет кандидатов: контракт, "
                "контактные лица, открытые позиции."
            ),
            "prompt": (
                "Извлекай клиента-компанию по упоминанию заказчика "
                "позиции с типом контракта.\n"
                "Примеры: «Acme — наш клиент по retainer-контракту» → "
                "client_company contract_type='retainer', "
                "status='active'.\n"
                "НЕ создавай client_company для собственной компании "
                "агентства."
            ),
            "required_fields": {},
            "optional_fields": {
                "contract_type": _enum_field(
                    label="Тип контракта",
                    description="Модель работы с клиентом",
                    values_with_desc=[
                        ("contingent", "contingent: оплата только за placement"),
                        ("retainer", "retainer: предоплата за процесс"),
                        ("rpo", "RPO: outsourcing полного процесса найма"),
                        ("exclusive", "эксклюзивный поиск"),
                    ],
                ),
                "status": _enum_field(
                    label="Статус клиента",
                    description="Активность сотрудничества",
                    values_with_desc=[
                        ("prospect", "потенциальный клиент"),
                        ("active", "активный клиент с позициями"),
                        ("paused", "сейчас нет позиций"),
                        ("churned", "перестал работать с агентством"),
                    ],
                ),
                "fee_pct": _number_field(
                    label="Гонорар, %",
                    description="Процент от годовой компенсации (для contingent).",
                ),
                "primary_contact": _string_field(
                    label="Главный контакт",
                    description="Имя ключевого hiring менеджера / HR на стороне клиента.",
                ),
            },
            "icon": "building",
            "color": "#37474F",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "position",
            "name": "Позиция (заказ)",
            "description": (
                "Вакансия от клиент-компании в работе у агентства: "
                "fee, дедлайн закрытия, статус заказа."
            ),
            "prompt": (
                "Извлекай позицию-заказ с привязкой к клиент-компании.\n"
                "Примеры: «Acme прислали заказ на Senior PM, fee 25%, "
                "дедлайн 60 дней» → position fee_pct=25, "
                "deadline_days=60.\n"
                "НЕ создавай position без понимания, для какого клиента "
                "ищется."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус заказа",
                    description="Состояние позиции в воронке",
                    values_with_desc=[
                        ("intake", "intake: уточняем требования с клиентом"),
                        ("active", "активный поиск"),
                        ("submissions", "submitted кандидаты на ревью у клиента"),
                        ("interviewing", "клиент проводит интервью"),
                        ("offer", "оформляется офер"),
                        ("placed", "закрыта placement'ом"),
                        ("on_hold", "приостановлена"),
                        ("cancelled", "отменена клиентом"),
                    ],
                ),
            },
            "optional_fields": {
                "level": _string_field(
                    label="Уровень",
                    description="Грейд (junior/middle/senior/lead/exec).",
                ),
                "fee_pct": _number_field(
                    label="Fee, %",
                    description="Процент гонорара по этой позиции.",
                ),
                "deadline_days": _integer_field(
                    label="Дедлайн, дн",
                    description="SLA по закрытию: сколько дней с приёма заказа.",
                ),
                "salary_range": _string_field(
                    label="Вилка",
                    description="Зарплатная вилка по позиции (gross).",
                ),
            },
            "icon": "folder",
            "color": "#455A64",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "candidate",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Кандидат",
            "description": (
                "Кандидат в базе агентства, потенциально подходит на "
                "несколько позиций. Подтип задачи: ведётся по agency funnel."
            ),
            "prompt": (
                "Извлекай нового кандидата с указанием стека и текущей "
                "стадии в работе агентства.\n"
                "Примеры: «Иван — Senior Backend на Go, готов к "
                "submission» → candidate stage='ready', skills=['Go', "
                "'Backend'].\n"
                "НЕ создавай candidate без имени и без минимального "
                "контекста подходимости."
            ),
            "required_fields": {
                "stage": _enum_field(
                    label="Стадия",
                    description="Воронка работы с кандидатом в агентстве",
                    values_with_desc=[
                        ("sourced", "найден в базе/LinkedIn"),
                        ("contacted", "сделан первый контакт"),
                        ("screened", "прошёл скрининг рекрутёра"),
                        ("ready", "готов к submission на позиции"),
                        ("submitted", "отправлен клиенту"),
                        ("interviewing", "клиент проводит интервью"),
                        ("offer", "клиент сделал офер"),
                        ("placed", "вышел в клиент-компанию"),
                        ("rejected", "отказали клиент или мы"),
                        ("withdrawn", "сам снялся"),
                    ],
                ),
            },
            "optional_fields": {
                "skills": _array_field(
                    label="Навыки",
                    description="Ключевые технологии/навыки в формате массива.",
                ),
                "salary_expectation": _number_field(
                    label="Ожидания",
                    description="Ожидаемая компенсация (gross/year).",
                ),
                "currency": _currency_field(),
                "notice_period_weeks": _integer_field(
                    label="Notice period, нед",
                    description="Сколько недель ему нужно для выхода после офера.",
                ),
            },
            "icon": "user",
            "color": "#5E35B1",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "submission",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Submission",
            "description": (
                "Отправка конкретного кандидата на конкретную позицию: "
                "статус ревью клиентом, фидбек."
            ),
            "prompt": (
                "Извлекай submission по упоминанию отправки кандидата на "
                "позицию клиенту.\n"
                "Примеры: «Submitted Ивана на Acme Senior PM» → "
                "submission status='sent'.\n"
                "НЕ создавай submission без указания и кандидата, и "
                "позиции."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Стадия ревью submission'а клиентом",
                    values_with_desc=[
                        ("sent", "отправлен клиенту"),
                        ("under_review", "клиент изучает резюме"),
                        ("interview_scheduled", "назначено интервью"),
                        ("rejected", "клиент отказал"),
                        ("hired", "превращён в placement"),
                    ],
                ),
            },
            "optional_fields": {
                "feedback": _text_field(
                    label="Фидбек клиента",
                    description="Что клиент сказал по этому кандидату.",
                ),
                "rejected_reason": _string_field(
                    label="Причина отказа",
                    description="Если status=rejected — кратко почему.",
                ),
            },
            "icon": "doc-detail",
            "color": "#5C6BC0",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "placement",
            "name": "Placement",
            "description": (
                "Успешное трудоустройство кандидата клиенту: дата выхода, "
                "fee, гарантийный период."
            ),
            "prompt": (
                "Извлекай placement по факту выхода кандидата к клиенту.\n"
                "Примеры: «Иван вышел в Acme 1 мая, fee $30k» → "
                "placement start_date=2024-05-01, fee_amount=30000, "
                "currency='USD'.\n"
                "НЕ создавай placement до фактического выхода кандидата "
                "(до этого — submission/offer)."
            ),
            "required_fields": {},
            "optional_fields": {
                "start_date": _date_field(
                    label="Дата выхода",
                    description="Когда кандидат фактически вышел к клиенту.",
                ),
                "fee_amount": _number_field(
                    label="Сумма гонорара",
                    description="Гонорар агентства по этому placement'у.",
                ),
                "currency": _currency_field(),
                "guarantee_until": _date_field(
                    label="Гарантия до",
                    description="Дата, до которой действует гарантия замены.",
                ),
                "status": _enum_field(
                    label="Статус placement'а",
                    description="Что происходит с placement'ом",
                    values_with_desc=[
                        ("active", "активный, в гарантийном периоде"),
                        ("guarantee_expired", "гарантия истекла, всё ок"),
                        ("replaced", "была замена в гарантийный период"),
                        ("refunded", "возвращён рефанд клиенту"),
                    ],
                ),
            },
            "icon": "chart",
            "color": "#388E3C",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:candidate": {
                "stages": [
                    {"id": "sourced", "label": "Sourced", "color": "#90A4AE"},
                    {"id": "contacted", "label": "Contacted", "color": "#42A5F5"},
                    {"id": "screened", "label": "Screened", "color": "#7E57C2"},
                    {"id": "ready", "label": "Ready", "color": "#26A69A"},
                    {"id": "submitted", "label": "Submitted", "color": "#5C6BC0"},
                    {"id": "interviewing", "label": "Interviewing", "color": "#1976D2"},
                    {"id": "offer", "label": "Offer", "color": "#FB8C00"},
                    {"id": "placed", "label": "Placed", "color": "#66BB6A"},
                    {"id": "rejected", "label": "Rejected", "color": "#BDBDBD"},
                    {"id": "withdrawn", "label": "Withdrawn", "color": "#9E9E9E"},
                ]
            },
            "task:submission": {
                "stages": [
                    {"id": "sent", "label": "Sent", "color": "#90A4AE"},
                    {"id": "under_review", "label": "Under review", "color": "#7E57C2"},
                    {"id": "interview_scheduled", "label": "Interview", "color": "#42A5F5"},
                    {"id": "rejected", "label": "Rejected", "color": "#BDBDBD"},
                    {"id": "hired", "label": "Hired", "color": "#66BB6A"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: real_estate
# ----------------------------------------------------------------------


_SEED_REAL_ESTATE = {
    "template_id": "real_estate",
    "name": "Недвижимость",
    "description": (
        "Брокеры и агентства недвижимости: объекты, лиды, показы, "
        "собственники и сделки. Готовые доски жизненного цикла объекта "
        "и сделки."
    ),
    "icon": "building",
    "types": [
        {
            "type_id": "property",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Объект",
            "description": (
                "Конкретный объект недвижимости: адрес, площадь, цена, "
                "статус. Подтип задачи: ведётся по property lifecycle."
            ),
            "prompt": (
                "Извлекай объект недвижимости по упоминанию адреса/типа/"
                "цены.\n"
                "Примеры: «2-комн. на Ленина 5, 50м², 8 млн ₽, "
                "доступна» → property kind='residential', "
                "area_sqm=50, price=8000000, currency='RUB', "
                "status='available'.\n"
                "НЕ создавай property без минимальной идентификации "
                "(адрес или жк/название)."
            ),
            "required_fields": {
                "kind": _enum_field(
                    label="Тип",
                    description="Категория недвижимости",
                    values_with_desc=[
                        ("residential", "жилая: квартира, дом, апартаменты"),
                        ("commercial", "коммерческая: офис, ритейл"),
                        ("industrial", "склад / производство"),
                        ("land", "земельный участок"),
                        ("hospitality", "гостиничная / hospitality"),
                    ],
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл объекта",
                    values_with_desc=[
                        ("available", "доступен"),
                        ("under_offer", "идёт оформление сделки"),
                        ("reserved", "забронирован"),
                        ("sold", "продан"),
                        ("rented", "сдан в аренду"),
                        ("withdrawn", "снят с продажи"),
                    ],
                ),
            },
            "optional_fields": {
                "address": _string_field(
                    label="Адрес",
                    description="Полный адрес объекта.",
                ),
                "area_sqm": _number_field(
                    label="Площадь, м²",
                    description="Общая площадь объекта.",
                ),
                "price": _number_field(
                    label="Цена",
                    description="Текущая цена объекта.",
                ),
                "currency": _currency_field(),
                "bedrooms": _integer_field(
                    label="Спальни",
                    description="Число спален (для residential).",
                ),
                "year_built": _integer_field(
                    label="Год постройки",
                    description="Год сдачи в эксплуатацию.",
                ),
                "listing_url": _string_field(
                    label="Ссылка на объявление",
                    description="URL на публичное объявление.",
                ),
            },
            "icon": "building",
            "color": "#558B2F",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "lead",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Лид",
            "description": (
                "Заявка от потенциального покупателя или арендатора с "
                "бюджетом, целью и предпочтениями. Подтип задачи."
            ),
            "prompt": (
                "Извлекай лид по упоминанию интереса с целью и бюджетом.\n"
                "Примеры: «Семья ищет 2-комн. до 10 млн в Хамовниках» → "
                "lead intent='buy', budget=10000000, currency='RUB', "
                "preferred_area='Хамовники'.\n"
                "НЕ создавай lead для общих обсуждений рынка без "
                "конкретного запроса."
            ),
            "required_fields": {
                "intent": _enum_field(
                    label="Цель",
                    description="Что хочет лид",
                    values_with_desc=[
                        ("buy", "купить"),
                        ("sell", "продать"),
                        ("rent", "арендовать"),
                        ("rent_out", "сдать"),
                        ("invest", "инвестировать"),
                    ],
                ),
                "stage": _enum_field(
                    label="Стадия",
                    description="Воронка работы с лидом",
                    values_with_desc=[
                        ("new", "только пришёл"),
                        ("qualified", "квалифицирован"),
                        ("touring", "идут показы"),
                        ("negotiating", "идут переговоры"),
                        ("offer_sent", "отправлено предложение"),
                        ("won", "сделка состоялась"),
                        ("lost", "проиграна"),
                    ],
                ),
            },
            "optional_fields": {
                "budget": _number_field(
                    label="Бюджет",
                    description="Максимальный бюджет лида.",
                ),
                "currency": _currency_field(),
                "preferred_area": _string_field(
                    label="Район",
                    description="Желаемый район/локация.",
                ),
                "preferences": _text_field(
                    label="Предпочтения",
                    description="Доп. требования: этаж, парковка, отделка и т.п.",
                ),
            },
            "icon": "target-lock",
            "color": "#33691E",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "viewing",
            "parent_type_id": MEETING_ENTITY_TYPE_ID,
            "name": "Показ",
            "description": (
                "Запланированный/состоявшийся показ объекта лиду. "
                "Подтип встречи."
            ),
            "prompt": (
                "Извлекай показ по упоминанию визита лида на объект.\n"
                "Примеры: «Показ на Ленина 5 завтра 18:00 для семьи "
                "Ивановых» → viewing scheduled_at='завтра 18:00'.\n"
                "НЕ создавай viewing для общего обсуждения объекта."
            ),
            "required_fields": {},
            "optional_fields": {
                "scheduled_at": _datetime_field(
                    label="Время показа",
                    description="Когда назначен или прошёл показ.",
                ),
                "outcome": _enum_field(
                    label="Результат",
                    description="Что вышло по итогам показа",
                    values_with_desc=[
                        ("interested", "лид заинтересовался"),
                        ("not_interested", "не подошло"),
                        ("undecided", "думает"),
                        ("no_show", "лид не пришёл"),
                    ],
                ),
                "feedback": _text_field(
                    label="Фидбек",
                    description="Что сказал лид по итогам показа.",
                ),
            },
            "icon": "users",
            "color": "#7CB342",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "owner",
            "name": "Собственник",
            "description": (
                "Собственник или представитель собственника объекта."
            ),
            "prompt": (
                "Извлекай собственника по упоминанию владельца объекта "
                "или его представителя.\n"
                "Примеры: «Собственник Иван Иванов, контракт "
                "эксклюзивный» → owner contract_type='exclusive'.\n"
                "НЕ путай с lead типа 'sell' — owner это уже "
                "подтверждённый собственник, заключивший договор."
            ),
            "required_fields": {},
            "optional_fields": {
                "contract_type": _enum_field(
                    label="Тип контракта",
                    description="На каких условиях работаем",
                    values_with_desc=[
                        ("exclusive", "эксклюзивный договор"),
                        ("non_exclusive", "не эксклюзивный"),
                        ("open_listing", "open listing"),
                    ],
                ),
                "commission_pct": _number_field(
                    label="Комиссия, %",
                    description="Комиссия агентства по договору.",
                ),
            },
            "icon": "user",
            "color": "#827717",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "agent",
            "name": "Агент",
            "description": (
                "Агент со стороны другой стороны сделки или партнёр "
                "(co-broking)."
            ),
            "prompt": (
                "Извлекай агента, представляющего другую сторону сделки "
                "или партнёра по co-broking.\n"
                "Примеры: «Со стороны покупателя — агент Маша из Best "
                "Realty» → agent + связь belongs_to organization "
                "'Best Realty'.\n"
                "НЕ создавай agent для своего сотрудника (это member)."
            ),
            "required_fields": {},
            "optional_fields": {
                "company": _string_field(
                    label="Агентство",
                    description="Название агентства/брокера, на которое работает.",
                ),
                "commission_split_pct": _number_field(
                    label="Доля комиссии, %",
                    description="Доля от общей комиссии в случае co-broking.",
                ),
            },
            "icon": "user",
            "color": "#4E342E",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:property": {
                "stages": [
                    {"id": "available", "label": "Available", "color": "#66BB6A"},
                    {"id": "under_offer", "label": "Under offer", "color": "#FB8C00"},
                    {"id": "reserved", "label": "Reserved", "color": "#FFB74D"},
                    {"id": "sold", "label": "Sold", "color": "#388E3C"},
                    {"id": "rented", "label": "Rented", "color": "#0288D1"},
                    {"id": "withdrawn", "label": "Withdrawn", "color": "#BDBDBD"},
                ]
            },
            "task:lead": {
                "stages": [
                    {"id": "new", "label": "New", "color": "#90A4AE"},
                    {"id": "qualified", "label": "Qualified", "color": "#7E57C2"},
                    {"id": "touring", "label": "Touring", "color": "#42A5F5"},
                    {"id": "negotiating", "label": "Negotiating", "color": "#FB8C00"},
                    {"id": "offer_sent", "label": "Offer sent", "color": "#FFA726"},
                    {"id": "won", "label": "Won", "color": "#66BB6A"},
                    {"id": "lost", "label": "Lost", "color": "#BDBDBD"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: legal
# ----------------------------------------------------------------------


_SEED_LEGAL = {
    "template_id": "legal",
    "name": "Юридическая практика",
    "description": (
        "Юридическая команда / in-house: matters, контракты, "
        "контрагенты, ключевые условия и сроки. Готовые доски matter "
        "lifecycle и contract review."
    ),
    "icon": "doc-detail",
    "types": [
        {
            "type_id": "matter",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Дело (matter)",
            "description": (
                "Юридическое дело: M&A, спор, IP-регистрация, employment "
                "вопрос. Подтип задачи; якорь для всех связанных "
                "контрактов и заметок."
            ),
            "prompt": (
                "Извлекай дело по упоминанию юридической задачи с областью "
                "и стороной.\n"
                "Примеры: «Открыли matter по M&A с Acme» → matter "
                "area='corporate', status='active'.\n"
                "НЕ создавай matter для разовой консультации без "
                "длительной работы."
            ),
            "required_fields": {
                "area": _enum_field(
                    label="Область",
                    description="Юридическая область",
                    values_with_desc=[
                        ("corporate", "корпоративное право, M&A"),
                        ("litigation", "судебные споры"),
                        ("ip", "интеллектуальная собственность"),
                        ("employment", "трудовое право"),
                        ("contracts", "договорная работа"),
                        ("compliance", "комплаенс / GDPR / 152-ФЗ"),
                        ("regulatory", "регуляторика отрасли"),
                        ("real_estate", "недвижимость"),
                        ("tax", "налоговая практика"),
                        ("other", "другая практика"),
                    ],
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл matter",
                    values_with_desc=[
                        ("intake", "приём, оценка работы"),
                        ("open", "открыт"),
                        ("active", "активная работа"),
                        ("on_hold", "приостановлен"),
                        ("closed", "закрыт успешно"),
                        ("lost", "проигран / отрицательный исход"),
                    ],
                ),
            },
            "optional_fields": {
                "client": _string_field(
                    label="Клиент",
                    description="Чьи интересы представляем.",
                ),
                "opposing_party": _string_field(
                    label="Контрсторона",
                    description="Кто оппонент в деле.",
                ),
                "lead_lawyer": _string_field(
                    label="Lead lawyer",
                    description="Имя ведущего юриста по matter.",
                ),
                "external_counsel": _string_field(
                    label="Внешний counsel",
                    description="Внешняя фирма-партнёр, если привлекалась.",
                ),
                "estimated_close_date": _date_field(
                    label="Ожидаемое закрытие",
                    description="Когда планируется завершение matter.",
                ),
            },
            "icon": "folder",
            "color": "#283593",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "contract",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Договор",
            "description": (
                "Договор / соглашение со сторонами, эффективной датой, "
                "сроком и финансовыми условиями. Подтип задачи: ведётся "
                "по contract review workflow."
            ),
            "prompt": (
                "Извлекай договор по упоминанию контракта/соглашения с "
                "сторонами и сроками.\n"
                "Примеры: «Подписали NDA с Acme от 1 марта на 3 года» → "
                "contract kind='nda', effective_date=2024-03-01, "
                "expiry_date=2027-03-01, status='signed'.\n"
                "НЕ создавай contract для устных договорённостей без "
                "оформления."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл договора",
                    values_with_desc=[
                        ("drafting", "черновик / шаблон"),
                        ("in_review", "на ревью у юристов"),
                        ("redlining", "redlining / правки сторон"),
                        ("approved", "утверждён внутри"),
                        ("signed", "подписан"),
                        ("active", "действует"),
                        ("expired", "срок действия истёк"),
                        ("terminated", "расторгнут досрочно"),
                    ],
                ),
            },
            "optional_fields": {
                "kind": _enum_field(
                    label="Тип договора",
                    description="Категория договора",
                    values_with_desc=[
                        ("nda", "NDA / соглашение о неразглашении"),
                        ("msa", "MSA / рамочное соглашение"),
                        ("sow", "SOW / scope of work"),
                        ("license", "лицензионный"),
                        ("employment", "трудовой / контрактор"),
                        ("partnership", "партнёрский / реселлер"),
                        ("vendor", "договор с поставщиком"),
                        ("dpa", "DPA / соглашение об обработке ПДн"),
                        ("settlement", "мировое соглашение"),
                        ("other", "другой"),
                    ],
                ),
                "value": _number_field(
                    label="Сумма договора",
                    description="Финансовое значение договора.",
                ),
                "currency": _currency_field(),
                "effective_date": _date_field(
                    label="Дата вступления в силу",
                    description="Когда договор начинает действовать.",
                ),
                "expiry_date": _date_field(
                    label="Дата окончания",
                    description="Когда договор истекает.",
                ),
                "auto_renew": _boolean_field(
                    label="Авто-пролонгация",
                    description="True, если договор автоматически продлевается без действий.",
                ),
                "governing_law": _string_field(
                    label="Применимое право",
                    description="Юрисдикция/право, регулирующее договор.",
                ),
            },
            "icon": "doc-detail",
            "color": "#1A237E",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "party",
            "name": "Сторона договора",
            "description": (
                "Контрагент: компания или физическое лицо в договоре. "
                "Не путать с organization — у party могут быть "
                "юридически значимые реквизиты."
            ),
            "prompt": (
                "Извлекай сторону договора, если в тексте есть юридическое "
                "имя или реквизиты контрагента.\n"
                "Примеры: «Контрагент: ООО Ромашка, ИНН 7710...» → party "
                "legal_name='ООО Ромашка', tax_id='7710...'.\n"
                "НЕ путай с organization (бренд) — party хранит "
                "формальные реквизиты для договора."
            ),
            "required_fields": {},
            "optional_fields": {
                "legal_name": _string_field(
                    label="Юридическое имя",
                    description="Полное юридическое наименование стороны.",
                ),
                "tax_id": _string_field(
                    label="Налоговый ID",
                    description="ИНН / VAT / EIN стороны.",
                ),
                "registered_address": _text_field(
                    label="Юридический адрес",
                    description="Адрес регистрации стороны.",
                ),
                "signatory": _string_field(
                    label="Подписант",
                    description="ФИО и должность подписанта от стороны.",
                ),
            },
            "icon": "user",
            "color": "#3F51B5",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "clause",
            "name": "Ключевое условие",
            "description": (
                "Существенное условие договора с риск-уровнем: "
                "ответственность, indemnification, неустойки и т.п."
            ),
            "prompt": (
                "Извлекай ключевые условия с риск-уровнем по тексту "
                "договора.\n"
                "Примеры: «Ответственность ограничена suммой контракта» "
                "→ clause kind='liability', risk_level='medium'.\n"
                "НЕ создавай clause для каждого пункта договора — "
                "только для существенных рисков."
            ),
            "required_fields": {},
            "optional_fields": {
                "kind": _enum_field(
                    label="Категория",
                    description="Вид условия",
                    values_with_desc=[
                        ("liability", "ответственность / лимит"),
                        ("indemnification", "indemnification"),
                        ("termination", "расторжение"),
                        ("payment", "платежи / неустойки"),
                        ("ip", "права на ИС"),
                        ("confidentiality", "конфиденциальность"),
                        ("non_compete", "non-compete / неконкуренция"),
                        ("data_protection", "обработка данных"),
                        ("warranty", "гарантии"),
                        ("other", "другое"),
                    ],
                ),
                "risk_level": _enum_field(
                    label="Риск",
                    description="Уровень риска условия для нашей стороны",
                    values_with_desc=[
                        ("low", "низкий: стандартная формулировка"),
                        ("medium", "средний: требует контроля"),
                        ("high", "высокий: эскалация юристам / лицам, принимающим решения"),
                    ],
                ),
                "summary": _text_field(
                    label="Суть",
                    description="Краткая суть условия в 1–3 предложения.",
                ),
            },
            "icon": "doc-detail",
            "color": "#303F9F",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "deadline",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Юр. дедлайн",
            "description": (
                "Критичный юридический срок: подача в суд, ответ "
                "регулятору, продление лицензии. Подтип задачи."
            ),
            "prompt": (
                "Извлекай юридический дедлайн с явной датой и риском "
                "пропуска.\n"
                "Примеры: «До 15 апреля подать иск, иначе пропуск срока "
                "исковой давности» → deadline statutory=true, "
                "due_date=2024-04-15.\n"
                "НЕ создавай deadline для обычных рабочих сроков — "
                "это task."
            ),
            "required_fields": {},
            "optional_fields": {
                "due_date": _date_field(
                    label="Срок",
                    description="К какой дате нужно совершить действие.",
                ),
                "statutory": _boolean_field(
                    label="Процессуальный",
                    description="True, если срок установлен законом и его пропуск имеет правовые последствия.",
                ),
                "consequence": _text_field(
                    label="Последствие",
                    description="Что произойдёт при пропуске срока.",
                ),
            },
            "icon": "error",
            "color": "#C62828",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:matter": {
                "stages": [
                    {"id": "intake", "label": "Intake", "color": "#90A4AE"},
                    {"id": "open", "label": "Open", "color": "#42A5F5"},
                    {"id": "active", "label": "Active", "color": "#7E57C2"},
                    {"id": "on_hold", "label": "On hold", "color": "#FFB74D"},
                    {"id": "closed", "label": "Closed", "color": "#66BB6A"},
                    {"id": "lost", "label": "Lost", "color": "#BDBDBD"},
                ]
            },
            "task:contract": {
                "stages": [
                    {"id": "drafting", "label": "Drafting", "color": "#90A4AE"},
                    {"id": "in_review", "label": "In review", "color": "#7E57C2"},
                    {"id": "redlining", "label": "Redlining", "color": "#FB8C00"},
                    {"id": "approved", "label": "Approved", "color": "#26A69A"},
                    {"id": "signed", "label": "Signed", "color": "#66BB6A"},
                    {"id": "active", "label": "Active", "color": "#388E3C"},
                    {"id": "expired", "label": "Expired", "color": "#9E9E9E"},
                    {"id": "terminated", "label": "Terminated", "color": "#EF5350"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: finance
# ----------------------------------------------------------------------


_SEED_FINANCE = {
    "template_id": "finance",
    "name": "Финансы",
    "description": (
        "Финансовая команда: счета на оплату и от поставщиков, "
        "командировочные/расходы, поставщики, бюджеты. Готовые доски "
        "invoice и expense workflows."
    ),
    "icon": "chart",
    "types": [
        {
            "type_id": "invoice",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Счёт",
            "description": (
                "Счёт на оплату: входящий (от поставщика) или исходящий "
                "(клиенту). Подтип задачи: ведётся по invoice workflow."
            ),
            "prompt": (
                "Извлекай счёт с направлением, суммой и сроком оплаты.\n"
                "Примеры: «Acme выставил счёт $5k, оплата до 15 апреля» → "
                "invoice direction='incoming', amount=5000, "
                "currency='USD', due_date=2024-04-15, status='sent'.\n"
                "НЕ создавай invoice для устных договорённостей без "
                "номера/документа."
            ),
            "required_fields": {
                "direction": _enum_field(
                    label="Направление",
                    description="Чей счёт: входящий от поставщика или исходящий клиенту",
                    values_with_desc=[
                        ("incoming", "входящий (мы должны заплатить)"),
                        ("outgoing", "исходящий (нам должны заплатить)"),
                    ],
                ),
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл счёта",
                    values_with_desc=[
                        ("drafted", "черновик"),
                        ("sent", "отправлен / получен"),
                        ("approved", "согласован к оплате"),
                        ("paid", "оплачен"),
                        ("partially_paid", "частично оплачен"),
                        ("overdue", "просрочен"),
                        ("voided", "аннулирован"),
                        ("disputed", "оспаривается"),
                    ],
                ),
            },
            "optional_fields": {
                "invoice_number": _string_field(
                    label="Номер счёта",
                    description="Номер документа.",
                ),
                "amount": _number_field(
                    label="Сумма",
                    description="Сумма счёта в указанной валюте.",
                ),
                "currency": _currency_field(),
                "issue_date": _date_field(
                    label="Дата выставления",
                    description="Когда счёт выставлен.",
                ),
                "due_date": _date_field(
                    label="Срок оплаты",
                    description="К какой дате счёт должен быть оплачен.",
                ),
                "paid_at": _date_field(
                    label="Дата оплаты",
                    description="Когда счёт фактически оплачен.",
                ),
                "tax_amount": _number_field(
                    label="Налог",
                    description="Сумма НДС / налога в счёте.",
                ),
            },
            "icon": "doc-detail",
            "color": "#0277BD",
            "is_event": True,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "expense",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Расход",
            "description": (
                "Заявка на возмещение командировочных или операционных "
                "расходов. Подтип задачи: ведётся по expense approval."
            ),
            "prompt": (
                "Извлекай расход с категорией, суммой и статусом "
                "согласования.\n"
                "Примеры: «Командировка в Питер, 12k ₽, ждёт "
                "согласования» → expense category='travel', "
                "amount=12000, currency='RUB', status='submitted'.\n"
                "НЕ создавай expense для общего обсуждения без заявки."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Стадия согласования расхода",
                    values_with_desc=[
                        ("draft", "черновик"),
                        ("submitted", "подан на согласование"),
                        ("approved", "согласован"),
                        ("rejected", "отклонён"),
                        ("reimbursed", "возмещён"),
                        ("cancelled", "отменён"),
                    ],
                ),
            },
            "optional_fields": {
                "category": _enum_field(
                    label="Категория",
                    description="К чему относится расход",
                    values_with_desc=[
                        ("travel", "командировки / транспорт"),
                        ("meals", "питание / представительские"),
                        ("software", "софт / SaaS"),
                        ("hardware", "техника / оборудование"),
                        ("training", "обучение / конференции"),
                        ("marketing", "маркетинг"),
                        ("office", "офисные расходы"),
                        ("legal", "юридические услуги"),
                        ("other", "другое"),
                    ],
                ),
                "amount": _number_field(
                    label="Сумма",
                    description="Сумма расхода.",
                ),
                "currency": _currency_field(),
                "incurred_on": _date_field(
                    label="Дата расхода",
                    description="Когда расход был произведён.",
                ),
                "receipt_url": _string_field(
                    label="Чек",
                    description="Ссылка на скан/фото чека.",
                ),
            },
            "icon": "doc-detail",
            "color": "#01579B",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "vendor",
            "name": "Поставщик",
            "description": (
                "Поставщик товаров/услуг: реквизиты, контакт-менеджер, "
                "история счетов."
            ),
            "prompt": (
                "Извлекай поставщика по упоминанию вендора с типом услуг.\n"
                "Примеры: «Поставщик хостинга — Yandex Cloud» → vendor "
                "kind='cloud'.\n"
                "НЕ создавай vendor для разовой покупки в магазине."
            ),
            "required_fields": {},
            "optional_fields": {
                "kind": _string_field(
                    label="Тип услуг",
                    description="Что поставляет: SaaS, оборудование, услуги, аренда…",
                ),
                "payment_terms_days": _integer_field(
                    label="Платёжные условия, дн",
                    description="Net N: сколько дней после счёта до оплаты.",
                ),
                "preferred_payment_method": _enum_field(
                    label="Метод оплаты",
                    description="Удобный способ оплаты",
                    values_with_desc=[
                        ("bank_transfer", "банковский перевод"),
                        ("card", "корп. карта"),
                        ("invoice", "по счёту"),
                        ("crypto", "криптовалюта"),
                    ],
                ),
            },
            "icon": "building",
            "color": "#2E7D32",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "budget",
            "name": "Бюджет",
            "description": (
                "Утверждённый бюджет на период по категории/проекту: "
                "лимит, потрачено, остаток."
            ),
            "prompt": (
                "Извлекай бюджет с периодом, категорией и лимитом.\n"
                "Примеры: «Q3 бюджет на маркетинг — $50k» → budget "
                "period='Q3 2024', category='marketing', amount=50000, "
                "currency='USD'.\n"
                "НЕ создавай бюджет без явного лимита."
            ),
            "required_fields": {
                "period": _string_field(
                    label="Период",
                    description="Период бюджета: Q1, H1, FY и год.",
                ),
            },
            "optional_fields": {
                "category": _string_field(
                    label="Категория",
                    description="К чему относится бюджет: маркетинг, R&D, операции…",
                ),
                "amount": _number_field(
                    label="Лимит",
                    description="Утверждённая сумма бюджета.",
                ),
                "currency": _currency_field(),
                "spent": _number_field(
                    label="Потрачено",
                    description="Текущая сумма освоения бюджета.",
                ),
                "owner_role": _string_field(
                    label="Владелец",
                    description="Кто отвечает за исполнение бюджета.",
                ),
            },
            "icon": "chart",
            "color": "#388E3C",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "transaction",
            "name": "Транзакция",
            "description": (
                "Финансовая операция: платёж, поступление, движение "
                "между счетами."
            ),
            "prompt": (
                "Извлекай транзакцию по упоминанию факта движения денег.\n"
                "Примеры: «Поступление 50k ₽ от Acme 12 марта» → "
                "transaction direction='credit', amount=50000, "
                "currency='RUB', occurred_on=2024-03-12.\n"
                "НЕ создавай transaction до фактического движения "
                "денег (план — это invoice)."
            ),
            "required_fields": {
                "direction": _enum_field(
                    label="Направление",
                    description="Тип операции",
                    values_with_desc=[
                        ("credit", "поступление / приход"),
                        ("debit", "списание / расход"),
                        ("transfer", "перевод между своими счетами"),
                    ],
                ),
            },
            "optional_fields": {
                "amount": _number_field(
                    label="Сумма",
                    description="Сумма операции.",
                ),
                "currency": _currency_field(),
                "occurred_on": _date_field(
                    label="Дата операции",
                    description="Когда транзакция фактически произошла.",
                ),
                "account": _string_field(
                    label="Счёт",
                    description="Какой банковский счёт затронут.",
                ),
                "category": _string_field(
                    label="Категория",
                    description="Категория для управленческого учёта.",
                ),
            },
            "icon": "chart",
            "color": "#1B5E20",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:invoice": {
                "stages": [
                    {"id": "drafted", "label": "Drafted", "color": "#90A4AE"},
                    {"id": "sent", "label": "Sent", "color": "#42A5F5"},
                    {"id": "approved", "label": "Approved", "color": "#26A69A"},
                    {"id": "paid", "label": "Paid", "color": "#66BB6A"},
                    {"id": "partially_paid", "label": "Partially paid", "color": "#FFB74D"},
                    {"id": "overdue", "label": "Overdue", "color": "#EF5350"},
                    {"id": "voided", "label": "Voided", "color": "#BDBDBD"},
                    {"id": "disputed", "label": "Disputed", "color": "#FB8C00"},
                ]
            },
            "task:expense": {
                "stages": [
                    {"id": "draft", "label": "Draft", "color": "#90A4AE"},
                    {"id": "submitted", "label": "Submitted", "color": "#42A5F5"},
                    {"id": "approved", "label": "Approved", "color": "#26A69A"},
                    {"id": "rejected", "label": "Rejected", "color": "#BDBDBD"},
                    {"id": "reimbursed", "label": "Reimbursed", "color": "#66BB6A"},
                    {"id": "cancelled", "label": "Cancelled", "color": "#9E9E9E"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Seed: education
# ----------------------------------------------------------------------


_SEED_EDUCATION = {
    "template_id": "education",
    "name": "Образование",
    "description": (
        "Образовательная команда / курс: курсы, уроки, задания, "
        "студенты, преподаватели и когорты. Готовые доски lesson plan и "
        "assignment grading."
    ),
    "icon": "doc-detail",
    "types": [
        {
            "type_id": "course",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Курс",
            "description": (
                "Учебный курс с уровнем, длительностью и статусом. "
                "Якорь для всех уроков, заданий и когорт."
            ),
            "prompt": (
                "Извлекай курс по упоминанию учебного продукта с уровнем "
                "и длительностью.\n"
                "Примеры: «Запускаем курс по продакт-менеджменту, 12 "
                "недель, level=intermediate» → course duration_weeks=12, "
                "level='intermediate', status='active'.\n"
                "НЕ создавай курс для одного урока (это lesson) или "
                "одного семинара (это meeting)."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл курса",
                    values_with_desc=[
                        ("planned", "запланирован, идёт подготовка"),
                        ("enrollment", "идёт набор студентов"),
                        ("active", "идёт обучение"),
                        ("completed", "очередной поток завершён"),
                        ("archived", "снят с продаж"),
                    ],
                ),
            },
            "optional_fields": {
                "level": _enum_field(
                    label="Уровень",
                    description="Уровень курса",
                    values_with_desc=[
                        ("beginner", "для новичков, без опыта"),
                        ("intermediate", "средний уровень"),
                        ("advanced", "продвинутый: для практиков"),
                        ("expert", "экспертный: для лидов/архитекторов"),
                    ],
                ),
                "format": _enum_field(
                    label="Формат",
                    description="Формат проведения",
                    values_with_desc=[
                        ("self_paced", "self-paced: каждый сам, без жёсткого расписания"),
                        ("cohort", "cohort-based: с группой и расписанием"),
                        ("live", "live-сессии в реальном времени"),
                        ("hybrid", "hybrid: смесь записей и live"),
                    ],
                ),
                "duration_weeks": _integer_field(
                    label="Длительность, нед",
                    description="Сколько недель идёт курс.",
                ),
                "price": _number_field(
                    label="Цена",
                    description="Цена курса для студента.",
                ),
                "currency": _currency_field(),
            },
            "icon": "layers",
            "color": "#6A1B9A",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "lesson",
            "parent_type_id": MEETING_ENTITY_TYPE_ID,
            "name": "Урок",
            "description": (
                "Учебная единица в курсе: лекция, семинар, мастер-класс. "
                "Подтип встречи."
            ),
            "prompt": (
                "Извлекай урок по упоминанию занятия с темой и форматом.\n"
                "Примеры: «Лекция 5 — discovery interviews, 18 марта 19:00» "
                "→ lesson kind='lecture', sequence=5, "
                "scheduled_at=2024-03-18T19:00.\n"
                "НЕ создавай lesson для общего митинга команды (это "
                "meeting)."
            ),
            "required_fields": {},
            "optional_fields": {
                "kind": _enum_field(
                    label="Тип урока",
                    description="Формат учебной единицы",
                    values_with_desc=[
                        ("lecture", "лекция"),
                        ("seminar", "семинар / разбор"),
                        ("workshop", "воркшоп / практикум"),
                        ("masterclass", "мастер-класс"),
                        ("qa", "Q&A / разбор вопросов"),
                        ("self_study", "самостоятельная работа"),
                    ],
                ),
                "sequence": _integer_field(
                    label="Номер",
                    description="Порядковый номер урока в курсе.",
                ),
                "scheduled_at": _datetime_field(
                    label="Дата проведения",
                    description="Когда запланирован/прошёл урок.",
                ),
                "duration_minutes": _integer_field(
                    label="Длительность, мин",
                    description="Сколько длится урок в минутах.",
                ),
                "recording_url": _string_field(
                    label="Запись",
                    description="Ссылка на запись урока, если есть.",
                ),
            },
            "icon": "doc-detail",
            "color": "#5E35B1",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "assignment",
            "parent_type_id": TASK_ROOT_ENTITY_TYPE_ID,
            "name": "Задание",
            "description": (
                "Задание для студента в курсе с дедлайном и оценкой. "
                "Подтип задачи: ведётся по grading workflow."
            ),
            "prompt": (
                "Извлекай задание по упоминанию учебного задания со "
                "сроком сдачи.\n"
                "Примеры: «ДЗ к уроку 5 — провести интервью, дедлайн "
                "25 марта» → assignment due_date=2024-03-25, "
                "max_points=10.\n"
                "НЕ создавай assignment для рабочей задачи команды "
                "(это task)."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Стадия проверки задания",
                    values_with_desc=[
                        ("assigned", "выдано студентам"),
                        ("submitted", "сдано студентом"),
                        ("under_review", "проверяется ментором"),
                        ("graded", "проверено и оценено"),
                        ("returned_for_rework", "возвращено на доработку"),
                        ("late", "просрочено"),
                    ],
                ),
            },
            "optional_fields": {
                "due_date": _date_field(
                    label="Дедлайн",
                    description="К какой дате задание должно быть сдано.",
                ),
                "max_points": _number_field(
                    label="Макс. баллов",
                    description="Максимальная возможная оценка.",
                ),
                "grade": _number_field(
                    label="Полученная оценка",
                    description="Финальная оценка после проверки.",
                ),
                "rubric_url": _string_field(
                    label="Критерии оценки",
                    description="Ссылка на rubric / критерии оценивания.",
                ),
            },
            "icon": "checklist",
            "color": "#7B1FA2",
            "is_event": False,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
        {
            "type_id": "student",
            "name": "Студент",
            "description": (
                "Учащийся на курсе с привязкой к когорте."
            ),
            "prompt": (
                "Извлекай студента, если в тексте есть имя учащегося с "
                "контекстом обучения.\n"
                "Примеры: «Иван из cohort-12 не сдал ДЗ» → student "
                "cohort='cohort-12'.\n"
                "НЕ создавай student для упоминания преподавателя (это "
                "instructor) или потенциального участника (это lead)."
            ),
            "required_fields": {},
            "optional_fields": {
                "cohort": _string_field(
                    label="Когорта",
                    description="Название/идентификатор когорты студента.",
                ),
                "background": _string_field(
                    label="Бэкграунд",
                    description="Краткое описание опыта/специализации студента.",
                ),
                "goal": _text_field(
                    label="Цель обучения",
                    description="Зачем студент идёт на курс.",
                ),
                "progress_pct": _number_field(
                    label="Прогресс, %",
                    description="Процент пройденного курса (0–100).",
                ),
            },
            "icon": "user",
            "color": "#9C27B0",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "instructor",
            "name": "Преподаватель",
            "description": (
                "Преподаватель / ментор курса: специализация, "
                "распределение по урокам."
            ),
            "prompt": (
                "Извлекай преподавателя по упоминанию ведущего/ментора "
                "курса.\n"
                "Примеры: «Маша ведёт продактовский трек» → instructor "
                "specialization='Product'.\n"
                "НЕ создавай instructor для разового приглашённого "
                "спикера без долгосрочного участия."
            ),
            "required_fields": {},
            "optional_fields": {
                "specialization": _string_field(
                    label="Специализация",
                    description="Тематическая область преподавателя.",
                ),
                "bio": _text_field(
                    label="Bio",
                    description="Короткое описание опыта преподавателя.",
                ),
                "rate_per_hour": _number_field(
                    label="Ставка / час",
                    description="Ставка преподавателя за час работы.",
                ),
                "currency": _currency_field(),
            },
            "icon": "user-shield",
            "color": "#673AB7",
            "is_event": False,
            "check_duplicates": True,
            "is_context_anchor": False,
        },
        {
            "type_id": "cohort",
            "name": "Когорта",
            "description": (
                "Поток студентов одного запуска курса с датами начала и "
                "окончания. Якорь для студентов и уроков потока."
            ),
            "prompt": (
                "Извлекай когорту по упоминанию запуска курса с датами/"
                "идентификатором.\n"
                "Примеры: «Cohort-12 стартует 1 апреля» → cohort "
                "start_date=2024-04-01, status='running'.\n"
                "НЕ создавай когорту без идентификатора и без явных "
                "дат запуска."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Жизненный цикл когорты",
                    values_with_desc=[
                        ("planned", "запланирована"),
                        ("enrollment", "идёт набор"),
                        ("running", "идёт обучение"),
                        ("completed", "завершена"),
                        ("cancelled", "отменена"),
                    ],
                ),
            },
            "optional_fields": {
                "start_date": _date_field(
                    label="Старт",
                    description="Дата старта когорты.",
                ),
                "end_date": _date_field(
                    label="Окончание",
                    description="Дата окончания когорты.",
                ),
                "capacity": _integer_field(
                    label="Capacity",
                    description="Максимальное число студентов в когорте.",
                ),
                "enrolled": _integer_field(
                    label="Зачислено",
                    description="Сколько студентов сейчас в когорте.",
                ),
            },
            "icon": "users",
            "color": "#512DA8",
            "is_event": True,
            "check_duplicates": True,
            "is_context_anchor": True,
        },
        {
            "type_id": "enrollment",
            "name": "Зачисление",
            "description": (
                "Факт записи студента в когорту со статусом прохождения."
            ),
            "prompt": (
                "Извлекай зачисление по упоминанию записи студента в "
                "когорту со статусом.\n"
                "Примеры: «Иван зачислен в cohort-12, активен» → "
                "enrollment status='active'.\n"
                "НЕ создавай enrollment без указания и студента, и "
                "когорты."
            ),
            "required_fields": {
                "status": _enum_field(
                    label="Статус",
                    description="Что происходит со студентом в когорте",
                    values_with_desc=[
                        ("enrolled", "зачислен, ещё не начал"),
                        ("active", "учится активно"),
                        ("paused", "взял паузу"),
                        ("completed", "успешно закончил"),
                        ("dropped", "отчислен / бросил"),
                        ("refunded", "возвращён рефанд"),
                    ],
                ),
            },
            "optional_fields": {
                "enrolled_on": _date_field(
                    label="Дата зачисления",
                    description="Когда студент был зачислен.",
                ),
                "completed_on": _date_field(
                    label="Дата завершения",
                    description="Когда студент закончил курс.",
                ),
                "final_grade": _number_field(
                    label="Итоговая оценка",
                    description="Финальная оценка за курс.",
                ),
            },
            "icon": "doc-detail",
            "color": "#311B92",
            "is_event": True,
            "check_duplicates": False,
            "is_context_anchor": False,
        },
    ],
    "crm_settings": {
        "default_note_voice": "self",
        "show_note_voice_ui": True,
        "pipeline_stage_presets": {
            "task": {
                "stages": [
                    {"id": "todo", "label": "К выполнению", "color": "#90A4AE"},
                    {"id": "in_progress", "label": "В работе", "color": "#42A5F5"},
                    {"id": "blocked", "label": "Заблокировано", "color": "#EF5350"},
                    {"id": "done", "label": "Готово", "color": "#66BB6A"},
                ]
            },
            "task:assignment": {
                "stages": [
                    {"id": "assigned", "label": "Assigned", "color": "#90A4AE"},
                    {"id": "submitted", "label": "Submitted", "color": "#42A5F5"},
                    {"id": "under_review", "label": "Under review", "color": "#7E57C2"},
                    {"id": "graded", "label": "Graded", "color": "#66BB6A"},
                    {"id": "returned_for_rework", "label": "Rework", "color": "#FB8C00"},
                    {"id": "late", "label": "Late", "color": "#EF5350"},
                ]
            },
        },
    },
}


# ----------------------------------------------------------------------
# Финальный список seed-пакетов
# ----------------------------------------------------------------------


NAMESPACE_TEMPLATE_SEEDS: list[dict[str, Any]] = [
    _SEED_SALES,
    _SEED_AGILE,
    _SEED_DEVELOPMENT,
    _SEED_HR,
    _SEED_MARKETING,
    _SEED_SUPPORT,
    _SEED_PRODUCT,
    _SEED_RECRUITING,
    _SEED_REAL_ESTATE,
    _SEED_LEGAL,
    _SEED_FINANCE,
    _SEED_EDUCATION,
]


# Каждый seed расширяется типами `note` и `task`, если их нет (они нужны
# каждому пространству — это инвариант). Якоря topic/organization/project
# подкладываем для всех пакетов как общий контекст.
for _seed in NAMESPACE_TEMPLATE_SEEDS:
    _seed["types"] = list(_seed["types"]) + COMMON_NAMESPACE_ANCHOR_TYPES

_ensure_namespace_template_seeds_contain_core_note_task(NAMESPACE_TEMPLATE_SEEDS)
