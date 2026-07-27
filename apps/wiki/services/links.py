"""
Извлечение исходящих ссылок страницы.

Ссылки считаются из содержимого при каждом сохранении и полностью заменяют
предыдущий набор: убранное из текста упоминание обязано исчезнуть и с карточки
сущности в Networkle, иначе связи начнут врать.
"""

from __future__ import annotations

from typing import Final

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.markdown_serializer import PLATFORM_FILE_SCHEME
from apps.wiki.content.prosemirror import ProseMirrorNode, iter_nodes
from apps.wiki.content.schema import WikiMentionKind
from apps.wiki.models.domain import WikiLinkTargetKind

_MENTION_KIND_TO_TARGET: Final[dict[WikiMentionKind, WikiLinkTargetKind]] = {
    WikiMentionKind.CRM_ENTITY: WikiLinkTargetKind.CRM_ENTITY,
    WikiMentionKind.WIKI_PAGE: WikiLinkTargetKind.WIKI_PAGE,
    WikiMentionKind.FILE: WikiLinkTargetKind.FILE,
}
"""Упоминания людей связями не считаются: пользователь не ресурс, на который
ведёт backlink, а адресат уведомления."""

_INTERNAL_LINK_SCHEMES: Final[dict[str, WikiLinkTargetKind]] = {
    "entity": WikiLinkTargetKind.CRM_ENTITY,
    "wiki": WikiLinkTargetKind.WIKI_PAGE,
    "file": WikiLinkTargetKind.FILE,
    "work-item": WikiLinkTargetKind.WORK_ITEM,
    "sync-message": WikiLinkTargetKind.SYNC_MESSAGE,
    PLATFORM_FILE_SCHEME: WikiLinkTargetKind.FILE,
}


class ExtractedLink(WikiBaseModel):
    """Ссылка, найденная в содержимом страницы."""

    target_kind: WikiLinkTargetKind
    target_id: str
    target_label: str = ""


class ExtractedMention(WikiBaseModel):
    """Упоминание пользователя — источник уведомления, не связи."""

    user_id: str
    label: str = ""


def extract_links(document: ProseMirrorNode) -> list[ExtractedLink]:
    """Собрать уникальные исходящие ссылки в порядке появления в тексте."""
    found: dict[tuple[str, str], ExtractedLink] = {}

    for node in iter_nodes(document):
        if node.type == "platform_mention":
            raw_kind = node.attrs.get("mention_kind")
            target_id = node.attrs.get("target_id")
            if not isinstance(raw_kind, str) or not isinstance(target_id, str) or not target_id:
                continue
            target_kind = _MENTION_KIND_TO_TARGET.get(WikiMentionKind(raw_kind))
            if target_kind is None:
                continue
            label = node.attrs.get("label")
            _ = found.setdefault(
                (target_kind.value, target_id),
                ExtractedLink(
                    target_kind=target_kind,
                    target_id=target_id,
                    target_label=label if isinstance(label, str) else "",
                ),
            )
            continue

        if node.type == "platform_file":
            file_id = node.attrs.get("file_id")
            if not isinstance(file_id, str) or not file_id:
                continue
            original_name = node.attrs.get("original_name")
            _ = found.setdefault(
                (WikiLinkTargetKind.FILE.value, file_id),
                ExtractedLink(
                    target_kind=WikiLinkTargetKind.FILE,
                    target_id=file_id,
                    target_label=original_name if isinstance(original_name, str) else "",
                ),
            )
            continue

        for mark in node.marks:
            if mark.type != "link":
                continue
            href = mark.attrs.get("href")
            if not isinstance(href, str) or not href:
                continue
            scheme, _, target = href.partition(":")
            target_kind = _INTERNAL_LINK_SCHEMES.get(scheme)
            if target_kind is None or not target:
                continue
            _ = found.setdefault(
                (target_kind.value, target),
                ExtractedLink(
                    target_kind=target_kind,
                    target_id=target,
                    target_label=node.text if node.text else "",
                ),
            )

    return list(found.values())


def extract_user_mentions(document: ProseMirrorNode) -> list[ExtractedMention]:
    """Упомянутые пользователи — кому отправлять уведомление."""
    found: dict[str, ExtractedMention] = {}
    for node in iter_nodes(document):
        if node.type != "platform_mention":
            continue
        raw_kind = node.attrs.get("mention_kind")
        target_id = node.attrs.get("target_id")
        if raw_kind != WikiMentionKind.USER.value:
            continue
        if not isinstance(target_id, str) or not target_id:
            continue
        label = node.attrs.get("label")
        _ = found.setdefault(
            target_id,
            ExtractedMention(user_id=target_id, label=label if isinstance(label, str) else ""),
        )
    return list(found.values())


__all__ = ["ExtractedLink", "ExtractedMention", "extract_links", "extract_user_mentions"]
