"""
Генератор демо-данных CRM для NetWorkle (продажа CRM B2B).

Пишет один JSON со схемой schema_version=1 для последующей загрузки в CRM через отдельный импортёр.
Связи и сущности используют стабильные logical_id; при создании через API CRM сервер выдаёт свои
entity_id (uuid) — импортёр должен построить отображение logical_id -> entity_id.

Запуск (из корня репозитория):
  uv run python scripts/generate_crm_sales_demo.py
  uv run python scripts/generate_crm_sales_demo.py --output my_demo.json

Требования к целевой компании перед импортом:
  - Namespace с именем из meta.target_namespace уже создан из шаблона sales (типы lead, deal).
  - Сущностные типы contact и organization созданы и разрешены в этом namespace (см. tests/crm/conftest.py).
  - Системные типы связей mentions, linked, related_to, belongs_to, follows_up доступны (инициализация компании).

Текст переговоров: полный диалог в description встречи (markdown-строки) и дублирующая структура
в attributes.transcript_turns (список объектов с speaker_role, speaker_name, text).
Обязательное для подтипа meeting поле attributes.participants — строка участников.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from core.clients.llm import get_llm
from core.logging import get_logger

logger = get_logger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

DEFAULT_MODEL = "qwen/qwen-turbo"
DEFAULT_NAMESPACE = "networkle_demo_sales"
DEFAULT_NUM_DEALS = 5
DEFAULT_MEETINGS_PER_DEAL = 20
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_DEAL_CONCURRENCY = 5
DEFAULT_OUTPUT_JSON = "demo_sales.json"
SCHEMA_VERSION = 1

# --- Экспорт JSON (контракт импорта) ---


class LogicalEntityExport(BaseModel):
    logical_id: str
    entity_type: str
    entity_subtype: str | None = None
    namespace: str
    name: str
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    note_date: str | None = None


class RelationshipExport(BaseModel):
    source_logical_id: str
    target_logical_id: str
    relationship_type: str
    namespace: str
    weight: float = 1.0


class DemoExportDocument(BaseModel):
    schema_version: int = SCHEMA_VERSION
    meta: dict[str, Any]
    networkl_roster: list[dict[str, str]]
    deal_briefs: list[dict[str, Any]]
    logical_entities: list[LogicalEntityExport]
    relationships: list[RelationshipExport]


# --- Ответы LLM ---


class ClientContactBrief(BaseModel):
    name: str
    role: str
    is_primary: bool


class DealBrief(BaseModel):
    organization_name: str
    industry: str
    amount_rub: float
    stage: str
    risks: str
    contacts: list[ClientContactBrief]
    meeting_dates: list[str]


class InitialBriefResponse(BaseModel):
    deals: list[DealBrief]


class DialogueTurn(BaseModel):
    speaker_role: str
    speaker_name: str
    text: str


class MeetingTranscriptResponse(BaseModel):
    participants_line: str
    decisions: str
    summary_for_next: str
    turns: list[DialogueTurn]


# --- Канонический состав Networkl (продавец) ---


@dataclass(frozen=True)
class RosterPerson:
    logical_id: str
    role_key: str
    name: str
    title: str


NETWORKL_ORG_LOGICAL = "org_networkl"

NETWORKL_ROSTER: list[RosterPerson] = [
    RosterPerson("contact_nl_ceo", "ceo", "Артём Верещагин", "CEO"),
    RosterPerson("contact_nl_cto", "cto", "Марина Крылова", "CTO"),
    RosterPerson("contact_nl_cpo", "cpo", "Илья Сазонов", "CPO"),
    RosterPerson("contact_nl_pm", "pm", "Елена Жукова", "Руководитель проектов"),
    RosterPerson("contact_nl_sales_0", "sales", "Дмитрий Орлов", "Менеджер по продажам"),
    RosterPerson("contact_nl_sales_1", "sales", "Светлана Никитина", "Менеджер по продажам"),
    RosterPerson("contact_nl_sales_2", "sales", "Константин Волков", "Менеджер по продажам"),
    RosterPerson("contact_nl_sales_3", "sales", "Ольга Ремизова", "Менеджер по продажам"),
    RosterPerson("contact_nl_sales_4", "sales", "Павел Ермаков", "Менеджер по продажам"),
    RosterPerson("contact_nl_tech_junior", "tech_junior", "Андрей Пестов", "Инженер внедрения (junior)"),
    RosterPerson("contact_nl_tech_mid", "tech_mid", "Наталья Громова", "Инженер внедрения (middle)"),
    RosterPerson("contact_nl_tech_senior", "tech_senior", "Виктор Панин", "Старший инженер"),
    RosterPerson("contact_nl_tech_lead", "tech_lead", "Георгий Майоров", "Тимлид внедрения"),
]

# Сделки 0 и 1 — Дмитрий Орлов (sales_0); далее по одной сделке на менеджера; Павел Ермаков — на совместных этапах
PRIMARY_SALES_INDEX_BY_DEAL: list[int] = [0, 0, 1, 2, 3]


def primary_sales_logical_id(deal_index: int) -> str:
    idx = PRIMARY_SALES_INDEX_BY_DEAL[deal_index]
    return NETWORKL_ROSTER[4 + idx].logical_id


def roster_by_role_key() -> dict[str, list[RosterPerson]]:
    bucket: dict[str, list[RosterPerson]] = {}
    for person in NETWORKL_ROSTER:
        bucket.setdefault(person.role_key, []).append(person)
    return bucket


# Индекс встречи 0..19 -> какие role_key со стороны Networkl присутствуют
MEETING_NETWORKL_ROLES: list[set[str]] = [
    {"sales"},
    {"sales", "pm"},
    {"sales", "cpo"},
    {"sales", "tech_mid"},
    {"sales", "tech_senior", "pm"},
    {"sales", "cto", "tech_senior"},
    {"sales", "tech_junior", "tech_mid"},
    {"sales", "cpo", "tech_lead"},
    {"sales", "sales_m4_extra", "pm"},
    {"sales", "cto", "tech_senior", "tech_lead"},
    {"sales", "pm", "tech_mid"},
    {"sales", "ceo", "cpo"},
    {"sales", "cto", "pm"},
    {"sales", "tech_senior", "tech_junior"},
    {"sales", "sales_m4_extra", "ceo"},
    {"sales", "pm", "tech_lead"},
    {"sales", "cto", "cpo"},
    {"sales", "ceo", "pm"},
    {"sales", "tech_lead", "tech_senior"},
    {"sales", "ceo", "cto", "cpo"},
]


MEETING_GOALS_RU: list[str] = [
    "Знакомство, цели внедрения CRM и ожидания от встречного цикла",
    "Сбор текущего процесса продаж и воронки",
    "Обзор возможностей продукта NetWorkle под отрасль заказчика",
    "Демо ключевых сценариев для роли sales и руководителя",
    "Технический обзор: интеграции, API, безопасность",
    "Воркшоп по миграции данных из текущих систем",
    "Оценка объёма кастомизаций и сроков пилота",
    "Согласование ролей и матрицы доступа",
    "Внутренняя синхронизация с участием ведущего методолога продаж (пятый менеджер)",
    "Глубокая проработка интеграции с email и календарём",
    "Пилот: план работ, критерии успеха, метрики",
    "Коммерческое предложение: структура лицензий и опций",
    "Юридические и закупочные требования заказчика",
    "Согласование дорожной карты внедрения",
    "Управленческая встреча: риски и эскалация (CEO + методолог)",
    "Финализация объёма пилота и ответственных",
    "Техническое закрытие вопросов по инфраструктуре",
    "Презентация для совета директоров заказчика (подготовка)",
    "Итоговые договорённости перед контрактом",
    "Финальное согласование следующих шагов и подписей",
]


def _networkl_people_for_meeting(meeting_index: int) -> list[RosterPerson]:
    roles = MEETING_NETWORKL_ROLES[meeting_index]
    by_key = roster_by_role_key()
    people: list[RosterPerson] = []
    for role in sorted(roles):
        if role == "sales_m4_extra":
            people.append(NETWORKL_ROSTER[8])
            continue
        for person in by_key.get(role, []):
            if person not in people:
                people.append(person)
    return people


def _uniq_by_name(items: list[ClientContactBrief]) -> list[ClientContactBrief]:
    seen: set[str] = set()
    out: list[ClientContactBrief] = []
    for item in items:
        if item.name in seen:
            continue
        seen.add(item.name)
        out.append(item)
    return out


def _client_contacts_for_meeting(
    contacts: list[ClientContactBrief],
    meeting_index: int,
) -> list[ClientContactBrief]:
    primary_list = [c for c in contacts if c.is_primary]
    primary_one = primary_list[0] if primary_list else contacts[0]
    others = [c for c in contacts if c.name != primary_one.name]

    if meeting_index <= 2:
        extra = [
            c
            for c in others
            if any(x in c.role.lower() for x in ("директор", "руковод", "ceo", "генерал"))
        ][:2]
        return _uniq_by_name([primary_one] + extra)

    if meeting_index <= 7:
        tech = [c for c in others if any(x in c.role.lower() for x in ("it", "ит", "тех", "сисадм", "cto"))]
        return _uniq_by_name([primary_one] + tech)

    if meeting_index <= 14:
        head = contacts[: max(3, len(contacts) // 2)]
        return _uniq_by_name(head)

    return contacts


SYSTEM_PROMPT_BRIEF = """Ты генератор структурированных демо-данных для CRM.
Ответ строго в JSON по схеме (structured output). Язык текстовых полей: русский.
Не используй реальные бренды и реальные компании РФ/мира — только вымышленные названия.
Суммы в рублях указывай как числа. Даты в формате ISO 8601 (только дата: YYYY-MM-DD).
Назначение менеджеров по сделкам зафиксировано в запросе пользователя — не меняй его."""

SYSTEM_PROMPT_MEETING = """Ты пишешь реалистичные демо-диалоги встреч B2B (продажа CRM NetWorkle).
Ответ строго в JSON по схеме. Русский язык.
Соблюдай уже заданные имена, роли, суммы и факты из контекста; не противоречь прошлым встречам.
Каждая реплика — содержательная, без воды; 8–18 реплик на встречу.
participants_line — одна строка со списком участников через запятую (имена как в контексте).
decisions — кратко что решили или зафиксировали.
summary_for_next — 3–5 предложений: итог и открытые пункты для следующей встречи."""


def _brief_user_message(num_deals: int, meetings_per_deal: int) -> str:
    lines = [
        f"Сгенерируй ровно {num_deals} независимых сделок (разные вымышленные компании-заказчики).",
        f"У каждой сделки ровно {meetings_per_deal} дат встреч meeting_dates (по одной на встречу), по возрастанию, с интервалом 3–10 рабочих дней.",
        "У каждой компании 3–5 контактов с разными ролями; ровно один контакт с is_primary=true.",
        "Назначение менеджеров NetWorkle по сделкам (уже решено, отрази в рисках или контексте stage, но не меняй логику):",
        "  Сделка 0 и 1 — ведущий менеджер Дмитрий Орлов;",
        "  Сделка 2 — Светлана Никитина;",
        "  Сделка 3 — Константин Волков;",
        "  Сделка 4 — Ольга Ремизова;",
        "  Павел Ермаков подключается точечно на методологических встречах (не как основной владелец сделки).",
        "Поля stage и risks должны отражать прогресс цикла продаж и быть согласованы с номером последней запланированной даты.",
    ]
    return "\n".join(lines)


def _meeting_user_message(
    deal_index: int,
    meeting_index: int,
    brief: DealBrief,
    primary_sales: RosterPerson,
    networkl_attendees: list[RosterPerson],
    client_attendees: list[ClientContactBrief],
    prev_summaries: list[str],
    last_decisions: str | None,
) -> str:
    goal = MEETING_GOALS_RU[meeting_index]
    nl_block = "\n".join(f"- {p.name} ({p.title})" for p in networkl_attendees)
    cl_block = "\n".join(f"- {c.name} ({c.role})" for c in client_attendees)
    prev_block = "\n".join(f"Встреча {i + 1}: {s}" for i, s in enumerate(prev_summaries))
    if not prev_block:
        prev_block = "(первая встреча по этой сделке — нет предыстории)"
    last_d = last_decisions or "(нет)"
    return f"""Сделка #{deal_index + 1}
Компания заказчик: {brief.organization_name}
Отрасль: {brief.industry}
Сумма сделки (ориентир): {brief.amount_rub} RUB
Стадия (из брифа): {brief.stage}
Риски (из брифа): {brief.risks}
Основной менеджер NetWorkle: {primary_sales.name}

Участники NetWorkle на этой встрече (говорят только они и заказчик из списка ниже):
{nl_block}

Участники со стороны заказчика (имена и роли):
{cl_block}

Цель встречи {meeting_index + 1} из {len(MEETING_GOALS_RU)}: {goal}

Краткие итоги прошлых встреч:
{prev_block}

Решения с прошлой встречи (если была):
{last_d}
"""


async def _llm_chat_structured(
    llm: Any,
    system: str,
    user: str,
    response_model: type[TModel],
    max_attempts: int,
    call_label: str = "",
) -> TModel:
    last_error: Exception | None = None
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if call_label:
        print(f"[demo] LLM «{call_label}» — отправка запроса…", flush=True)
    for attempt in range(max_attempts):
        try:
            t_req = time.perf_counter()
            result = await llm.chat(messages, response_model=response_model, temperature=0.35)
            elapsed = time.perf_counter() - t_req
            if call_label:
                print(
                    f"[demo] LLM «{call_label}» — ответ за {elapsed:.2f}s (попытка {attempt + 1}/{max_attempts})",
                    flush=True,
                )
            return result
        except Exception as exc:
            last_error = exc
            logger.warning("LLM structured call failed attempt %s: %s", attempt + 1, exc)
            if call_label:
                print(
                    f"[demo] LLM «{call_label}» — сбой попытки {attempt + 1}/{max_attempts}: {type(exc).__name__}: {exc}",
                    flush=True,
                )
    raise RuntimeError(f"LLM не вернул валидный structured ответ после {max_attempts} попыток") from last_error


def _validate_brief(response: InitialBriefResponse, num_deals: int, meetings_per_deal: int) -> None:
    if len(response.deals) != num_deals:
        raise ValueError(f"Ожидалось {num_deals} сделок в брифе, получено {len(response.deals)}")
    for i, deal in enumerate(response.deals):
        if len(deal.meeting_dates) != meetings_per_deal:
            raise ValueError(f"Сделка {i}: ожидалось {meetings_per_deal} дат, получено {len(deal.meeting_dates)}")
        if len(deal.contacts) < 3:
            raise ValueError(f"Сделка {i}: нужно минимум 3 контакта")
        if sum(1 for c in deal.contacts if c.is_primary) != 1:
            raise ValueError(f"Сделка {i}: ровно один контакт с is_primary=true")


def _format_meeting_description(turns: list[DialogueTurn]) -> str:
    parts: list[str] = []
    for turn in turns:
        parts.append(f"**{turn.speaker_name}** ({turn.speaker_role}):\n{turn.text}")
    return "\n\n".join(parts)


def _build_static_networkl_entities(namespace: str) -> list[LogicalEntityExport]:
    entities: list[LogicalEntityExport] = [
        LogicalEntityExport(
            logical_id=NETWORKL_ORG_LOGICAL,
            entity_type="organization",
            entity_subtype=None,
            namespace=namespace,
            name="NetWorkle",
            description="Поставщик CRM-платформы (демо-сценарий)",
            attributes={"country": "RU", "segment": "vendor"},
            tags=["demo", "networkl", "vendor"],
        )
    ]
    for person in NETWORKL_ROSTER:
        entities.append(
            LogicalEntityExport(
                logical_id=person.logical_id,
                entity_type="contact",
                entity_subtype=None,
                namespace=namespace,
                name=person.name,
                description=person.title,
                attributes={"title": person.title, "role_key": person.role_key},
                tags=["demo", "networkl", "staff"],
            )
        )
    return entities


def _relationship_networkl_belongs(namespace: str) -> list[RelationshipExport]:
    rels: list[RelationshipExport] = []
    for person in NETWORKL_ROSTER:
        rels.append(
            RelationshipExport(
                source_logical_id=person.logical_id,
                target_logical_id=NETWORKL_ORG_LOGICAL,
                relationship_type="belongs_to",
                namespace=namespace,
            )
        )
    return rels


async def _generate_one_deal_slice(
    llm: Any,
    namespace: str,
    d: int,
    b: DealBrief,
    meetings_per_deal: int,
    max_attempts: int,
    num_deals: int,
) -> tuple[dict[str, Any], list[LogicalEntityExport], list[RelationshipExport]]:
    """
    Одна сделка: org, lead, deal, контакты, встречи по порядку (цепочка summary).
    Параллелится с другими сделками на уровне generate_demo.
    """
    print(
        f"[demo] ▶ сделка {d + 1}/{num_deals} «{b.organization_name}»: старт пайплайна встреч",
        flush=True,
    )
    deal_brief_dump = b.model_dump(mode="json")
    entities: list[LogicalEntityExport] = []
    rels: list[RelationshipExport] = []

    org_lid = f"org_client_{d}"
    lead_lid = f"lead_{d}"
    deal_lid = f"deal_{d}"

    entities.append(
        LogicalEntityExport(
            logical_id=org_lid,
            entity_type="organization",
            entity_subtype=None,
            namespace=namespace,
            name=b.organization_name,
            description=f"Заказчик. Отрасль: {b.industry}. {b.risks}",
            attributes={"industry": b.industry},
            tags=["demo", "client"],
        )
    )
    entities.append(
        LogicalEntityExport(
            logical_id=lead_lid,
            entity_type="lead",
            entity_subtype=None,
            namespace=namespace,
            name=f"Лид: {b.organization_name}",
            description=b.risks,
            attributes={
                "source": "outbound_demo",
                "stage": b.stage,
            },
            tags=["demo", "lead"],
            assignees=[primary_sales_logical_id(d)],
        )
    )
    entities.append(
        LogicalEntityExport(
            logical_id=deal_lid,
            entity_type="deal",
            entity_subtype=None,
            namespace=namespace,
            name=f"Сделка: {b.organization_name}",
            description=b.risks,
            attributes={"amount": b.amount_rub, "stage": b.stage},
            tags=["demo", "deal"],
            assignees=[primary_sales_logical_id(d)],
        )
    )

    rels.append(
        RelationshipExport(
            source_logical_id=lead_lid,
            target_logical_id=deal_lid,
            relationship_type="related_to",
            namespace=namespace,
        )
    )
    rels.append(
        RelationshipExport(
            source_logical_id=deal_lid,
            target_logical_id=org_lid,
            relationship_type="related_to",
            namespace=namespace,
        )
    )

    for c_idx, c in enumerate(b.contacts):
        clid = f"contact_client_{d}_{c_idx}"
        entities.append(
            LogicalEntityExport(
                logical_id=clid,
                entity_type="contact",
                entity_subtype=None,
                namespace=namespace,
                name=c.name,
                description=c.role,
                attributes={"role": c.role, "is_primary": c.is_primary},
                tags=["demo", "client_contact"],
            )
        )
        rels.append(
            RelationshipExport(
                source_logical_id=clid,
                target_logical_id=org_lid,
                relationship_type="belongs_to",
                namespace=namespace,
            )
        )
        rels.append(
            RelationshipExport(
                source_logical_id=clid,
                target_logical_id=deal_lid,
                relationship_type="related_to",
                namespace=namespace,
            )
        )

    prev_summaries: list[str] = []
    last_decisions: str | None = None
    primary_sales_person = NETWORKL_ROSTER[4 + PRIMARY_SALES_INDEX_BY_DEAL[d]]

    for m in range(meetings_per_deal):
        meeting_label = (
            f"сделка {d + 1}/{num_deals} «{b.organization_name}», встреча {m + 1}/{meetings_per_deal}"
        )
        print(f"[demo]   → {meeting_label}: подготовка промпта…", flush=True)
        nl_people = _networkl_people_for_meeting(m)
        nl_people = [p for p in nl_people if p.role_key != "sales"]
        nl_people = [primary_sales_person] + nl_people

        cl_people = _client_contacts_for_meeting(b.contacts, m)
        user_msg = _meeting_user_message(
            d, m, b, primary_sales_person, nl_people, cl_people, prev_summaries, last_decisions
        )
        print(
            f"[demo]   → {meeting_label}: участников NetWorkle={len(nl_people)}, заказчик={len(cl_people)}",
            flush=True,
        )
        transcript = await _llm_chat_structured(
            llm,
            SYSTEM_PROMPT_MEETING,
            user_msg,
            MeetingTranscriptResponse,
            max_attempts,
            call_label=meeting_label,
        )
        print(
            f"[demo]   ✓ {meeting_label}: реплик в диалоге={len(transcript.turns)}",
            flush=True,
        )
        prev_summaries.append(transcript.summary_for_next)
        last_decisions = transcript.decisions

        meeting_lid = f"meeting_{d}_{m}"
        note_date = b.meeting_dates[m]
        desc = _format_meeting_description(transcript.turns)
        turns_dump = [t.model_dump() for t in transcript.turns]

        entities.append(
            LogicalEntityExport(
                logical_id=meeting_lid,
                entity_type="note",
                entity_subtype="meeting",
                namespace=namespace,
                name=f"Встреча {m + 1}: {b.organization_name}",
                description=desc,
                attributes={
                    "participants": transcript.participants_line,
                    "decisions": transcript.decisions,
                    "transcript_turns": turns_dump,
                    "deal_index": d,
                    "meeting_index": m,
                },
                tags=["demo", "meeting"],
                assignees=[primary_sales_logical_id(d)],
                note_date=note_date,
            )
        )
        rels.append(
            RelationshipExport(
                source_logical_id=meeting_lid,
                target_logical_id=deal_lid,
                relationship_type="related_to",
                namespace=namespace,
            )
        )
        if m > 0:
            rels.append(
                RelationshipExport(
                    source_logical_id=meeting_lid,
                    target_logical_id=f"meeting_{d}_{m - 1}",
                    relationship_type="follows_up",
                    namespace=namespace,
                )
            )

    print(
        f"[demo] ■ сделка {d + 1}/{num_deals} «{b.organization_name}»: все встречи готовы",
        flush=True,
    )
    return deal_brief_dump, entities, rels


async def generate_demo(
    *,
    model: str = DEFAULT_MODEL,
    namespace: str = DEFAULT_NAMESPACE,
    num_deals: int = DEFAULT_NUM_DEALS,
    meetings_per_deal: int = DEFAULT_MEETINGS_PER_DEAL,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    deal_concurrency: int = DEFAULT_DEAL_CONCURRENCY,
) -> DemoExportDocument:
    if meetings_per_deal > len(MEETING_GOALS_RU):
        raise ValueError(f"meetings_per_deal не больше {len(MEETING_GOALS_RU)}")
    if num_deals > len(PRIMARY_SALES_INDEX_BY_DEAL):
        raise ValueError(f"num_deals не больше {len(PRIMARY_SALES_INDEX_BY_DEAL)}")

    total_llm_calls = 1 + num_deals * meetings_per_deal
    concurrent_deals = deal_concurrency if deal_concurrency > 0 else num_deals
    concurrent_deals = min(concurrent_deals, num_deals)
    t_all = time.perf_counter()
    print(
        f"[demo] Старт: модель={model!r}, namespace={namespace!r}, "
        f"сделок={num_deals}, встреч/сделка={meetings_per_deal}, всего LLM-вызовов≈{total_llm_calls}; "
        f"сделки параллельно (одновременно до {concurrent_deals}), внутри сделки встречи строго по порядку",
        flush=True,
    )

    print("[demo] Инициализация LLM-клиента (get_llm)…", flush=True)
    llm = get_llm(model_name=model)
    print(f"[demo] LLM-клиент готов: {type(llm).__name__}", flush=True)

    brief = await _llm_chat_structured(
        llm,
        SYSTEM_PROMPT_BRIEF,
        _brief_user_message(num_deals, meetings_per_deal),
        InitialBriefResponse,
        max_attempts,
        call_label=f"бриф: {num_deals} сделок, даты встреч",
    )
    _validate_brief(brief, num_deals, meetings_per_deal)
    print("[demo] Бриф прошёл валидацию. Компании заказчиков:", flush=True)
    for i, deal in enumerate(brief.deals):
        print(f"  [{i + 1}] {deal.organization_name!r} ({deal.industry})", flush=True)

    logical_entities = _build_static_networkl_entities(namespace)
    relationships = _relationship_networkl_belongs(namespace)

    deal_briefs_dump: list[dict[str, Any]] = []
    roster_dump = [
        {"logical_id": p.logical_id, "role_key": p.role_key, "name": p.name, "title": p.title}
        for p in NETWORKL_ROSTER
    ]

    sem = asyncio.Semaphore(concurrent_deals)

    async def run_one_deal(
        d: int,
    ) -> tuple[dict[str, Any], list[LogicalEntityExport], list[RelationshipExport]]:
        async with sem:
            return await _generate_one_deal_slice(
                llm,
                namespace,
                d,
                brief.deals[d],
                meetings_per_deal,
                max_attempts,
                num_deals,
            )

    print(
        f"[demo] Запуск {num_deals} пайплайнов сделок (одновременно не более {concurrent_deals})…",
        flush=True,
    )
    t_deals = time.perf_counter()
    per_deal_results = await asyncio.gather(*[run_one_deal(d) for d in range(num_deals)])
    print(
        f"[demo] Все пайплайны сделок завершены за {time.perf_counter() - t_deals:.1f}s",
        flush=True,
    )

    for dump, ent_slice, rel_slice in per_deal_results:
        deal_briefs_dump.append(dump)
        logical_entities.extend(ent_slice)
        relationships.extend(rel_slice)

    meta = {
        "seller_company_name": "NetWorkle",
        "target_namespace": namespace,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "num_deals": num_deals,
        "meetings_per_deal": meetings_per_deal,
        "assignee_note": "Поля assignees содержат logical_id контактов; при импорте заменить на user_id платформы.",
        "primary_sales_by_deal": [
            {"deal_index": i, "contact_logical_id": primary_sales_logical_id(i)} for i in range(num_deals)
        ],
    }

    elapsed_all = time.perf_counter() - t_all
    print(
        f"[demo] Генерация завершена за {elapsed_all:.1f}s: "
        f"сущностей={len(logical_entities)}, связей={len(relationships)}",
        flush=True,
    )

    return DemoExportDocument(
        meta=meta,
        networkl_roster=roster_dump,
        deal_briefs=deal_briefs_dump,
        logical_entities=logical_entities,
        relationships=relationships,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Генерация демо JSON для CRM (NetWorkle sales).")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_JSON,
        help=f"Путь к выходному .json (по умолчанию {DEFAULT_OUTPUT_JSON})",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Имя модели LLM")
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help="Целевой namespace для сущностей в JSON",
    )
    parser.add_argument(
        "--deals",
        type=int,
        default=DEFAULT_NUM_DEALS,
        help="Число параллельных сделок (макс. 5)",
    )
    parser.add_argument(
        "--meetings-per-deal",
        type=int,
        default=DEFAULT_MEETINGS_PER_DEAL,
        help="Число встреч на сделку (макс. 20)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help="Повторы structured-вызова при ошибке парсинга/валидации",
    )
    parser.add_argument(
        "--deal-concurrency",
        type=int,
        default=DEFAULT_DEAL_CONCURRENCY,
        help="Сколько сделок гонять параллельно (0 = без лимита, фактически num_deals)",
    )
    args = parser.parse_args()

    print(
        f"[demo] CLI: output={args.output!r}, model={args.model!r}, deal_concurrency={args.deal_concurrency}",
        flush=True,
    )
    t_main = time.perf_counter()
    doc = asyncio.run(
        generate_demo(
            model=args.model,
            namespace=args.namespace,
            num_deals=args.deals,
            meetings_per_deal=args.meetings_per_deal,
            max_attempts=args.max_attempts,
            deal_concurrency=args.deal_concurrency,
        )
    )

    path = args.output
    print(f"[demo] Сериализация JSON → {path!r}…", flush=True)
    payload = doc.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    wall = time.perf_counter() - t_main
    print(f"[demo] Файл записан за {wall:.2f}s (включая генерацию). Готово.", flush=True)
    logger.info("Записано %s сущностей, %s связей в %s", len(doc.logical_entities), len(doc.relationships), path)


if __name__ == "__main__":
    main()
