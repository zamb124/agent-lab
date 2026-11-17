"""Платформенные тулы почты: ящики, членство, папки, письма, черновики, отправка.

Тонкие обёртки над ``core.clients.mail_client.MailClient`` → ``MailService``.
Вся авторизация — в сервисе (``can_view``/``can_send`` через AuthzService,
``require_company_admin`` для создания платформенного ящика), тул ничего
не решает сам. Секреты (``password``) принимаются только как аргументы и
никогда не возвращаются — публичная форма binding'а отдаёт ``has_password``.

Намеренно не покрыто: ``unbind_mailbox`` и ``delete_message`` — деструктивные
операции; мягкое удаление — ``mail_move_message`` с ``destination_role=trash``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator

from apps.flows.src.tools.decorator import tool
from core.clients.mail_client import MailClient
from core.mail.models import MailAttachment
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from apps.flows.src.state import ExecutionState

_TAGS = ["mail"]

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

_DESCRIPTIONS = {
    "list_bindings": """
Почтовые ящики активной компании, из которых текущий пользователь может
читать и отправлять (только доступные binding'и — `can_view`).

Ответ: `items` — полная публичная форма MailboxBinding
(`mailbox_binding_id`, `email_address`, `local_part`, `kind` `user`/`role`,
`is_default`, `sync_enabled`, `has_password`, IMAP/SMTP хосты).

Когда вызывать: узнать `mailbox_binding_id`/`local_part` для `mail_send`,
`mail_list_messages` и др., или проверить, что нужный role-ящик доступен.
""".strip(),
    "create_mailbox": """
Создать платформенный ящик на домене компании (только company admin —
MailPermissionError иначе). На сервере провижнится mailbox с паролем,
создаётся binding.

Параметры: `kind` (`role` — общий ящик типа sales/info/support;
`user` — личный ящик сотрудника, тогда `user_id` обязателен по смыслу),
`local_part` (часть до @; пусто → для `user` генерируется из slug),
`password` (опционально; иначе генерируется сервером),
`provision` (false → только binding без создания mailbox на сервере),
`is_default` (сделать дефолтным ящиком пользователя).

Ответ: публичная форма созданного MailboxBinding.
""".strip(),
    "connect_personal": """
Подключить произвольный внешний ящик по IMAP/SMTP (Gmail, Yandex, свой
сервер — любой провайдер): проверяет логин, создаёт personal connection +
binding, запускает первичный sync. После этого ящик доступен `mail_send`
и всем read-операциям.

Параметры: `email_address`, `password` (пароль приложения), `imap_host`,
`smtp_host`, `imap_port` (993), `smtp_port` (465), `use_ssl`,
`sync_enabled` (false → только отправка).

Ответ: публичная форма созданного MailboxBinding (`connection_scope=personal`).
""".strip(),
    "patch_binding": """
Обновить настройки существующего ящика: `sync_enabled`, `password`
(с проверкой логина), IMAP/SMTP хосты/порты, `user_id` (переназначение
владельца user-ящика, требует admin), `calendar_color`.

Ответ: публичная форма обновлённого MailboxBinding.
""".strip(),
    "set_default_binding": """
Сделать user-ящик дефолтным для его владельца (владелец ящика или admin).
Дефолтный ящик используется `mail_send`, когда отправитель не указан.

Ответ: публичная форма MailboxBinding.
""".strip(),
    "healthcheck_binding": """
Проверить, что логин ящика работает (только personal-mailbox; владелец
или admin). Опционально — новые `password`/хосты вместо сохранённых.

Ответ: `MailServerHealth` — `provider`, `imap_ok`, `smtp_ok`,
`provision_ok`, `detail`.
""".strip(),
    "list_members": """
Участники role-ящика (shared mailbox): кто имеет доступ помимо владельца.
Ответ: `items` — `user_id`, `role` (`member`/`manager`). Требует
admin-доступа к binding.
""".strip(),
    "add_member": """
Дать пользователю доступ к role-ящику: `user_id`, `role`
(`member` — чтение+отправка; `manager` — ещё и управление участниками).
Требует admin-доступа к binding. Ответ: созданный MailboxBindingMember.
""".strip(),
    "remove_member": """
Убрать доступ пользователя к role-ящику. Требует admin-доступа к binding.
Ответ: `removed=true`.
""".strip(),
    "list_folders": """
Папки ящика (local-first + IMAP): `folders[]` — `name`, `role`
(`inbox`/`sent`/`drafts`/`trash`/`junk`/`archive`/`other`), `delimiter`,
`unseen_count`, `message_count`; плюс `missing_standard_roles`, `needs_sync`.
""".strip(),
    "list_messages": """
Список писем в папке ящика (local-first из StoredMailMessage, быстро).
Параметры: `mailbox_binding_id`, `folder` (INBOX по умолчанию),
`limit` (1–200), `cursor` (пагинация).

Ответ: `items` — `uid`, `message_id`, `subject`, `from_address`, `snippet`,
`unread`, `flagged`, `date`, `attachment_count`; `next_cursor`, `has_more`,
`needs_sync` (true → вызови `mail_sync_now` и повтори).
""".strip(),
    "search_messages": """
Поиск писем по подстроке (тема/отправитель/тело): `q` обязателен,
опционально `folder`. Ответ — как у `mail_list_messages`.
""".strip(),
    "get_message": """
Полное письмо по `uid` (+`folder`): `subject`, `from_address`,
`to_addresses`, `body_text`, `body_html`, `attachments` (метаданные),
заголовки треда. Побочный эффект — письмо помечается прочитанным
(как при открытии в почтовом клиенте); вернуть — `mail_set_flags(seen=false)`.
""".strip(),
    "get_thread": """
Тред переписки, в которой участвует письмо `uid`: `items` — письма по
всем папкам с полями `folder`, `uid`; `participant_emails`.
Прочитанные письма помечаются seen (как при открытии треда).
""".strip(),
    "sync_now": """
Запустить синхронизацию ящика с IMAP прямо сейчас (refresh папок +
очередь sync). Ответ: `accepted=true`. Когда вызывать: после отправки,
перед проверкой ответов, при `needs_sync=true` у list/search.
""".strip(),
    "send": """
Отправить письмо через SMTP ящика активной компании. Внешний эффект —
требует preview-approval; покажи пользователю получателей и тему заранее.

Отправитель резолвится только среди доступных ящиков: `mailbox_binding_id`
или `from_local_part` (local-part ящика компании — role или user); без
обоих — default-ящик пользователя. Отправка из чужого ящика — ошибка.

Параметры:
- `to_addresses` (1–5 валидных email), `subject`, `body_text`
  (обязательная текстовая версия), `body_html` (опционально).
- `sender_display_name` — имя в `From` (`From: Name <addr@dom.tld>`).
- `in_reply_to`, `references` — Message-ID треда для ответа.
- `attachments` — файлы платформы: `[{file_id, filename, content_type}]`.

Ответ: `message_id`, `accepted`, `mailbox_binding_id`, `from_address`.
""".strip(),
    "save_draft": """
Сохранить письмо в папку Черновики (Drafts) ящика — без отправки.
Подходит для «подготовь, человек проверит и отправит».
`uid` — заменить существующий черновик. Ответ: `uid`, `folder`, `message_id`.
""".strip(),
    "set_flags": """
Изменить флаги письма: `seen` (true/false → прочитано/непрочитано),
`flagged` (true/false → звёздочка). Хотя бы один обязателен.
Ответ: `uid`, `unread`, `flagged`.
""".strip(),
    "move_message": """
Переместить письмо в другую папку: `destination_folder` (явное имя) или
`destination_role` (`trash`/`archive`/`junk`/`sent`/`drafts`/`inbox` —
имя резолвится под провайдера ящика). Ответ: `uid`, `folder`,
`destination_folder`, `destination_uid`.
""".strip(),
}


def _validate_addresses(value: JsonValue, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be an array of strings")
    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{field_name}[{index}] must be a string")
        address = item.strip().lower()
        if not _EMAIL_RE.match(address):
            raise ValueError(f"{field_name}[{index}] invalid email: {item!r}")
        out.append(address)
    return out


class _BindingArgs(StrictBaseModel):
    mailbox_binding_id: str = Field(..., min_length=1, description="ID ящика из mail_list_bindings.")


class MailListBindingsArgs(StrictBaseModel):
    """Accessible mailboxes — no args."""


class MailCreateMailboxArgs(StrictBaseModel):
    kind: Literal["role", "user"] = Field(
        default="role",
        description="role — общий ящик компании (sales/info/support); user — ящик сотрудника.",
    )
    local_part: str | None = Field(
        default=None,
        description="Часть до @ (например `sales`); для user пусто → slug пользователя.",
    )
    user_id: str | None = Field(default=None, description="Владелец user-ящика.")
    email_address: str | None = Field(
        default=None,
        description="Полный адрес (редко — иначе local_part@домен компании).",
    )
    password: str | None = Field(
        default=None, description="Пароль ящика; пусто → генерируется сервером."
    )
    provision: bool = Field(
        default=True, description="Создать mailbox на почтовом сервере (иначе только binding)."
    )
    sync_enabled: bool = Field(default=True, description="Включить IMAP-sync писем.")
    is_default: bool | None = Field(
        default=None, description="Сделать дефолтным ящиком владельца."
    )


class MailConnectPersonalArgs(StrictBaseModel):
    email_address: str = Field(..., min_length=3, description="Адрес внешнего ящика.")
    password: str = Field(..., min_length=1, description="Пароль/пароль приложения.")
    imap_host: str = Field(..., min_length=1, description="IMAP-сервер (imap.gmail.com).")
    smtp_host: str = Field(..., min_length=1, description="SMTP-сервер (smtp.gmail.com).")
    imap_port: int = Field(default=993, ge=1, le=65535, description="IMAP-порт.")
    smtp_port: int = Field(default=465, ge=1, le=65535, description="SMTP-порт.")
    use_ssl: bool = Field(default=True, description="SSL для IMAP/SMTP.")
    sync_enabled: bool = Field(default=True, description="Синхронизировать входящие.")

    @field_validator("email_address", mode="before")
    @classmethod
    def _check_email(cls, value: JsonValue) -> str:
        return _validate_addresses([value], "email_address")[0]


class MailPatchBindingArgs(_BindingArgs):
    sync_enabled: bool | None = Field(default=None, description="Вкл/выкл IMAP-sync.")
    password: str | None = Field(default=None, description="Новый пароль (проверяется логин).")
    imap_host: str | None = Field(default=None, description="Новый IMAP-сервер.")
    imap_port: int | None = Field(default=None, ge=1, le=65535, description="IMAP-порт.")
    smtp_host: str | None = Field(default=None, description="Новый SMTP-сервер.")
    smtp_port: int | None = Field(default=None, ge=1, le=65535, description="SMTP-порт.")
    use_ssl: bool | None = Field(default=None, description="SSL вкл/выкл.")
    user_id: str | None = Field(
        default=None, description="Переназначить владельца user-ящика (admin)."
    )
    calendar_color: str | None = Field(default=None, description="Цвет привязанного календаря.")


class MailHealthcheckArgs(_BindingArgs):
    password: str | None = Field(default=None, description="Новый пароль вместо сохранённого.")
    imap_host: str | None = Field(default=None, description="IMAP-сервер override.")
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = Field(default=None, description="SMTP-сервер override.")
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = Field(default=None)


class MailAddMemberArgs(_BindingArgs):
    user_id: str = Field(..., min_length=1, description="Пользователь компании.")
    role: Literal["member", "manager"] = Field(
        default="member",
        description="member — чтение+отправка; manager — ещё и управление участниками.",
    )


class MailRemoveMemberArgs(_BindingArgs):
    user_id: str = Field(..., min_length=1, description="Пользователь компании.")


class _FolderArgs(_BindingArgs):
    folder: str = Field(default="INBOX", description="Папка (INBOX, Sent, Trash...).")


class _MessageArgs(_FolderArgs):
    uid: str = Field(..., min_length=1, description="UID письма в folder.")


class MailListMessagesArgs(_FolderArgs):
    limit: int = Field(default=50, ge=1, le=200, description="Размер страницы.")
    cursor: str | None = Field(default=None, description="Курсор пагинации из next_cursor.")


class MailSearchMessagesArgs(_BindingArgs):
    q: str = Field(..., min_length=1, description="Подстрока поиска (тема/отправитель/тело).")
    folder: str | None = Field(
        default=None, description="Ограничить папкой; пусто — по всем."
    )
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None)


class MailAttachmentArgs(StrictBaseModel):
    file_id: str = Field(..., min_length=1, description="ID файла в Files платформы.")
    filename: str = Field(..., min_length=1, description="Имя файла в письме.")
    content_type: str = Field(..., min_length=1, description="MIME-тип (application/pdf).")


class MailSendArgs(StrictBaseModel):
    to_addresses: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Получатели — валидные email, 1–5 штук.",
    )
    subject: str = Field(..., min_length=1, description="Тема письма.")
    body_text: str = Field(..., min_length=1, description="Текстовая версия (обязательна).")
    body_html: str | None = Field(default=None, description="HTML-версия письма.")
    mailbox_binding_id: str | None = Field(
        default=None,
        description="Явный mailbox_binding_id отправителя; приоритет над from_local_part.",
    )
    from_local_part: str | None = Field(
        default=None,
        description="local_part ящика отправителя; role-матч предпочтителен.",
    )
    sender_display_name: str | None = Field(
        default=None,
        description="Имя отправителя в заголовке From.",
    )
    in_reply_to: str | None = Field(default=None, description="In-Reply-To Message-ID.")
    references: str | None = Field(default=None, description="References header.")
    attachments: list[MailAttachmentArgs] = Field(
        default_factory=list,
        description="Вложения из файлов платформы: file_id + filename + content_type.",
    )

    @field_validator("to_addresses", mode="before")
    @classmethod
    def _normalize_to_addresses(cls, value: JsonValue) -> list[str]:
        return _validate_addresses(value, "to_addresses")


class MailSaveDraftArgs(_BindingArgs):
    to_addresses: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Получатели; пусто → черновик на свой адрес.",
    )
    subject: str = Field(default="", description="Тема.")
    body_text: str = Field(default="", description="Текстовая версия.")
    body_html: str | None = Field(default=None, description="HTML-версия.")
    uid: str | None = Field(default=None, description="UID черновика для замены.")
    in_reply_to: str | None = Field(default=None)
    references: str | None = Field(default=None)

    @field_validator("to_addresses", mode="before")
    @classmethod
    def _normalize_to_addresses(cls, value: JsonValue) -> list[str]:
        return _validate_addresses(value, "to_addresses")


class MailSetFlagsArgs(_MessageArgs):
    seen: bool | None = Field(default=None, description="true → прочитано, false → непрочитано.")
    flagged: bool | None = Field(default=None, description="true/false → звёздочка.")


class MailMoveMessageArgs(_MessageArgs):
    destination_folder: str | None = Field(
        default=None, description="Явное имя целевой папки."
    )
    destination_role: Literal["trash", "archive", "junk", "sent", "drafts", "inbox"] | None = Field(
        default=None,
        description="Стандартная роль папки — имя резолвится под провайдера ящика.",
    )


@tool(
    name="mail_list_bindings",
    description=_DESCRIPTIONS["list_bindings"],
    tags=_TAGS,
    parameters_model=MailListBindingsArgs,
    effects=["read"],
)
async def mail_list_bindings(
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return {"items": await mail_client.list_accessible_bindings()}


@tool(
    name="mail_create_mailbox",
    description=_DESCRIPTIONS["create_mailbox"],
    tags=_TAGS,
    parameters_model=MailCreateMailboxArgs,
    effects=["create"],
    confirmation_floor="preview",
)
async def mail_create_mailbox(
    kind: Literal["role", "user"] = "role",
    local_part: str | None = None,
    user_id: str | None = None,
    email_address: str | None = None,
    password: str | None = None,
    provision: bool = True,
    sync_enabled: bool = True,
    is_default: bool | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.create_mailbox(
        kind=kind,
        local_part=local_part,
        user_id=user_id,
        email_address=email_address,
        password=password,
        provision=provision,
        sync_enabled=sync_enabled,
        is_default=is_default,
    )


@tool(
    name="mail_connect_personal",
    description=_DESCRIPTIONS["connect_personal"],
    tags=_TAGS,
    parameters_model=MailConnectPersonalArgs,
    effects=["create"],
    confirmation_floor="preview",
)
async def mail_connect_personal(
    email_address: str,
    password: str,
    imap_host: str,
    smtp_host: str,
    imap_port: int = 993,
    smtp_port: int = 465,
    use_ssl: bool = True,
    sync_enabled: bool = True,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.connect_personal(
        email_address=email_address,
        password=password,
        imap_host=imap_host,
        imap_port=imap_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        use_ssl=use_ssl,
        sync_enabled=sync_enabled,
    )


@tool(
    name="mail_patch_binding",
    description=_DESCRIPTIONS["patch_binding"],
    tags=_TAGS,
    parameters_model=MailPatchBindingArgs,
    effects=["update"],
    confirmation_floor="preview",
)
async def mail_patch_binding(
    mailbox_binding_id: str,
    sync_enabled: bool | None = None,
    password: str | None = None,
    imap_host: str | None = None,
    imap_port: int | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    use_ssl: bool | None = None,
    user_id: str | None = None,
    calendar_color: str | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.patch_binding(
        mailbox_binding_id,
        sync_enabled=sync_enabled,
        password=password,
        imap_host=imap_host,
        imap_port=imap_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        use_ssl=use_ssl,
        user_id=user_id,
        calendar_color=calendar_color,
    )


@tool(
    name="mail_set_default_binding",
    description=_DESCRIPTIONS["set_default_binding"],
    tags=_TAGS,
    parameters_model=_BindingArgs,
    effects=["update"],
)
async def mail_set_default_binding(
    mailbox_binding_id: str,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.set_default_binding(mailbox_binding_id)


@tool(
    name="mail_healthcheck_binding",
    description=_DESCRIPTIONS["healthcheck_binding"],
    tags=_TAGS,
    parameters_model=MailHealthcheckArgs,
    effects=["read"],
)
async def mail_healthcheck_binding(
    mailbox_binding_id: str,
    password: str | None = None,
    imap_host: str | None = None,
    imap_port: int | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    use_ssl: bool | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.healthcheck_binding(
        mailbox_binding_id,
        password=password,
        imap_host=imap_host,
        imap_port=imap_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        use_ssl=use_ssl,
    )


@tool(
    name="mail_list_members",
    description=_DESCRIPTIONS["list_members"],
    tags=_TAGS,
    parameters_model=_BindingArgs,
    effects=["read"],
)
async def mail_list_members(
    mailbox_binding_id: str,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return {"items": await mail_client.list_members(mailbox_binding_id)}


@tool(
    name="mail_add_member",
    description=_DESCRIPTIONS["add_member"],
    tags=_TAGS,
    parameters_model=MailAddMemberArgs,
    effects=["update"],
    confirmation_floor="preview",
)
async def mail_add_member(
    mailbox_binding_id: str,
    user_id: str,
    role: Literal["member", "manager"] = "member",
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.add_member(
        mailbox_binding_id, user_id=user_id, role=role
    )


@tool(
    name="mail_remove_member",
    description=_DESCRIPTIONS["remove_member"],
    tags=_TAGS,
    parameters_model=MailRemoveMemberArgs,
    effects=["update"],
    confirmation_floor="preview",
)
async def mail_remove_member(
    mailbox_binding_id: str,
    user_id: str,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.remove_member(mailbox_binding_id, user_id=user_id)


@tool(
    name="mail_list_folders",
    description=_DESCRIPTIONS["list_folders"],
    tags=_TAGS,
    parameters_model=_BindingArgs,
    effects=["read"],
)
async def mail_list_folders(
    mailbox_binding_id: str,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.list_folders(mailbox_binding_id)


@tool(
    name="mail_list_messages",
    description=_DESCRIPTIONS["list_messages"],
    tags=_TAGS,
    parameters_model=MailListMessagesArgs,
    effects=["read"],
)
async def mail_list_messages(
    mailbox_binding_id: str,
    folder: str = "INBOX",
    limit: int = 50,
    cursor: str | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.list_messages(
        mailbox_binding_id=mailbox_binding_id,
        folder=folder,
        limit=limit,
        cursor=cursor,
    )


@tool(
    name="mail_search_messages",
    description=_DESCRIPTIONS["search_messages"],
    tags=_TAGS,
    parameters_model=MailSearchMessagesArgs,
    effects=["read"],
)
async def mail_search_messages(
    mailbox_binding_id: str,
    q: str,
    folder: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.search_messages(
        mailbox_binding_id=mailbox_binding_id,
        q=q,
        folder=folder,
        limit=limit,
        cursor=cursor,
    )


@tool(
    name="mail_get_message",
    description=_DESCRIPTIONS["get_message"],
    tags=_TAGS,
    parameters_model=_MessageArgs,
    effects=["read"],
)
async def mail_get_message(
    mailbox_binding_id: str,
    uid: str,
    folder: str = "INBOX",
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.get_message(
        mailbox_binding_id=mailbox_binding_id, uid=uid, folder=folder
    )


@tool(
    name="mail_get_thread",
    description=_DESCRIPTIONS["get_thread"],
    tags=_TAGS,
    parameters_model=_MessageArgs,
    effects=["read"],
)
async def mail_get_thread(
    mailbox_binding_id: str,
    uid: str,
    folder: str = "INBOX",
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.get_thread(
        mailbox_binding_id=mailbox_binding_id, uid=uid, folder=folder
    )


@tool(
    name="mail_sync_now",
    description=_DESCRIPTIONS["sync_now"],
    tags=_TAGS,
    parameters_model=_BindingArgs,
    effects=["write"],
)
async def mail_sync_now(
    mailbox_binding_id: str,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.sync_now(mailbox_binding_id)


@tool(
    name="mail_send",
    description=_DESCRIPTIONS["send"],
    tags=_TAGS,
    parameters_model=MailSendArgs,
    effects=["write"],
    confirmation_floor="approval",
)
async def mail_send(
    to_addresses: list[str],
    subject: str,
    body_text: str,
    body_html: str | None = None,
    mailbox_binding_id: str | None = None,
    from_local_part: str | None = None,
    sender_display_name: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: list[MailAttachmentArgs] | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.send(
        to_addresses=to_addresses,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        mailbox_binding_id=mailbox_binding_id,
        from_local_part=from_local_part,
        sender_display_name=sender_display_name,
        in_reply_to=in_reply_to,
        references=references,
        attachments=[
            MailAttachment(
                file_id=item.file_id,
                filename=item.filename,
                content_type=item.content_type,
            )
            for item in (attachments or [])
        ],
    )


@tool(
    name="mail_save_draft",
    description=_DESCRIPTIONS["save_draft"],
    tags=_TAGS,
    parameters_model=MailSaveDraftArgs,
    effects=["create"],
    confirmation_floor="preview",
)
async def mail_save_draft(
    mailbox_binding_id: str,
    to_addresses: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    body_html: str | None = None,
    uid: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.save_draft(
        mailbox_binding_id=mailbox_binding_id,
        to_addresses=list(to_addresses or []),
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        uid=uid,
        in_reply_to=in_reply_to,
        references=references,
    )


@tool(
    name="mail_set_flags",
    description=_DESCRIPTIONS["set_flags"],
    tags=_TAGS,
    parameters_model=MailSetFlagsArgs,
    effects=["update"],
)
async def mail_set_flags(
    mailbox_binding_id: str,
    uid: str,
    folder: str = "INBOX",
    seen: bool | None = None,
    flagged: bool | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.set_flags(
        mailbox_binding_id=mailbox_binding_id,
        uid=uid,
        folder=folder,
        seen=seen,
        flagged=flagged,
    )


@tool(
    name="mail_move_message",
    description=_DESCRIPTIONS["move_message"],
    tags=_TAGS,
    parameters_model=MailMoveMessageArgs,
    effects=["update"],
    confirmation_floor="preview",
)
async def mail_move_message(
    mailbox_binding_id: str,
    uid: str,
    folder: str = "INBOX",
    destination_folder: str | None = None,
    destination_role: Literal["trash", "archive", "junk", "sent", "drafts", "inbox"] | None = None,
    *,
    state: "ExecutionState",
    mail_client: MailClient,
) -> JsonObject:
    _ = state
    return await mail_client.move_message(
        mailbox_binding_id=mailbox_binding_id,
        uid=uid,
        folder=folder,
        destination_folder=destination_folder,
        destination_role=destination_role,
    )
