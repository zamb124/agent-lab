"""
Медиа страниц публичного сайта.

Файлы платформы приватны: обычный роут скачивания сверяет компанию файла с
активной компанией запроса, а у анонимного посетителя её нет. Поэтому в
публичной выдаче ссылки на платформенные файлы заменяются на роут с токеном
сайта, а сам роут проверяет, что файл действительно лежит в содержимом
опубликованной страницы этого сайта.

Помечать файлы wiki публичными нельзя: тогда они были бы доступны по прямой
ссылке независимо от того, опубликована страница или нет.
"""

from __future__ import annotations

from apps.wiki.content.prosemirror import ProseMirrorAttrValue, ProseMirrorNode, iter_nodes
from apps.wiki.content.schema import FILE_NODE
from core.files.file_ref import file_id_from_download_url

IMAGE_NODE: str = "image"


def public_file_url(link_token: str, file_id: str, variant: str | None = None) -> str:
    """Ссылка на файл внутри публичного сайта.

    `variant` — платформенный вариант изображения `?v=` (см. files.mdc):
    ленивая WebP-материализация вместо отдачи оригинала.
    """
    url = f"/wiki/api/v1/public/pages/{link_token}/files/{file_id}"
    return f"{url}?v={variant}" if variant else url


def platform_file_id_from_url(url: str) -> str:
    """`file_id` из платформенной ссылки скачивания.

    Ссылка бывает и относительной, и абсолютной. Пустая строка означает, что
    адрес ведёт не в платформенное хранилище — внешние картинки и data URI
    переписывать не нужно.
    """
    if url == "":
        return ""
    parsed = file_id_from_download_url(url)
    if parsed is None:
        return ""
    return parsed


def _string_attr(attrs: dict[str, ProseMirrorAttrValue], name: str) -> str:
    if name not in attrs:
        return ""
    value = attrs[name]
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Attribute {name} of the document node must be a string")
    return value


def _image_file_id(attrs: dict[str, ProseMirrorAttrValue]) -> str:
    explicit = _string_attr(attrs, "file_id")
    if explicit != "":
        return explicit
    return platform_file_id_from_url(_string_attr(attrs, "src"))


def collect_file_ids(content: ProseMirrorNode) -> set[str]:
    """Все платформенные файлы, на которые ссылается документ."""
    collected: set[str] = set()
    for node in iter_nodes(content):
        if node.type == IMAGE_NODE:
            file_id = _image_file_id(node.attrs)
            if file_id != "":
                collected.add(file_id)
        elif node.type == FILE_NODE:
            file_id = _string_attr(node.attrs, "file_id")
            if file_id != "":
                collected.add(file_id)
    return collected


def rewrite_media_for_public(content: ProseMirrorNode, link_token: str) -> ProseMirrorNode:
    """Копия документа, где `src` картинок ведёт на роут сайта.

    Чип `platform_file` не трогаем: он хранит только `file_id`, а базу ссылки
    подставляет редактор — публичная страница передаёт ему свою.
    """
    children = [rewrite_media_for_public(child, link_token) for child in content.content]
    attrs = dict(content.attrs)
    if content.type == IMAGE_NODE:
        file_id = _image_file_id(content.attrs)
        if file_id != "":
            attrs["src"] = public_file_url(link_token, file_id, variant="lg")
            attrs["file_id"] = file_id
    return ProseMirrorNode(
        type=content.type,
        attrs=attrs,
        content=children,
        marks=list(content.marks),
        text=content.text,
    )


def rewrite_cover_for_public(cover_url: str, link_token: str) -> str:
    """Обложка: платформенный файл уходит на роут сайта, внешний URL остаётся."""
    file_id = platform_file_id_from_url(cover_url)
    if file_id == "":
        return cover_url
    return public_file_url(link_token, file_id, variant="lg")


__all__ = [
    "IMAGE_NODE",
    "collect_file_ids",
    "platform_file_id_from_url",
    "public_file_url",
    "rewrite_cover_for_public",
    "rewrite_media_for_public",
]
