"""
Права на страницы: наследование ограничений по дереву.

Ограничение ставится на страницу и распространяется на всё поддерево. Отсюда
же выводится видимость, которая решает, в какой слой RAG попадёт текст, —
поэтому разбор дерева проверяется отдельно от БД.
"""

from __future__ import annotations

import pytest

from apps.wiki.models.domain import WikiPagePermission, WikiVisibility
from apps.wiki.services.access import WikiAccessResolver

#   root
#   ├── public_child
#   └── restricted            (ограничение: reader — read, editor — write)
#       └── restricted_child  (наследует ограничение)
PARENTS: dict[str, str | None] = {
    "root": None,
    "public_child": "root",
    "restricted": "root",
    "restricted_child": "restricted",
}
OWNERS: dict[str, str] = {page_id: "owner" for page_id in PARENTS}
RESTRICTED: set[str] = {"restricted"}


def resolver_for(user_id: str | None, permission: WikiPagePermission | None) -> WikiAccessResolver:
    permissions = {"restricted": permission} if permission is not None else {}
    return WikiAccessResolver(
        parents=PARENTS,
        restricted_page_ids=RESTRICTED,
        user_permissions=permissions,
        page_owners=OWNERS,
        user_id=user_id,
    )


def test_unrestricted_page_is_visible_to_any_workspace_member():
    resolver = resolver_for("stranger", None)
    assert resolver.can_view("root") is True
    assert resolver.can_view("public_child") is True
    assert resolver.can_edit("public_child") is True


def test_restriction_hides_page_from_non_member():
    resolver = resolver_for("stranger", None)
    assert resolver.can_view("restricted") is False
    assert resolver.can_view("restricted_child") is False


def test_restriction_is_inherited_by_subtree():
    resolver = resolver_for("reader", WikiPagePermission.READ)
    assert resolver.visibility("restricted_child") == WikiVisibility.RESTRICTED
    assert resolver.can_view("restricted_child") is True
    assert resolver.can_edit("restricted_child") is False


def test_write_permission_on_ancestor_allows_editing_child():
    resolver = resolver_for("editor", WikiPagePermission.WRITE)
    assert resolver.can_edit("restricted_child") is True
    assert resolver.can_administer("restricted_child") is False


def test_admin_permission_allows_changing_access():
    resolver = resolver_for("boss", WikiPagePermission.ADMIN)
    assert resolver.can_administer("restricted") is True


def test_restriction_does_not_leak_to_siblings():
    resolver = resolver_for("stranger", None)
    assert resolver.visibility("public_child") == WikiVisibility.COMPANY
    assert resolver.nearest_restriction("public_child") is None


def test_nearest_restriction_points_to_source_page():
    resolver = resolver_for("reader", WikiPagePermission.READ)
    assert resolver.nearest_restriction("restricted_child") == "restricted"


def test_anonymous_user_sees_only_unrestricted_pages():
    resolver = resolver_for(None, None)
    assert resolver.can_view("public_child") is True
    assert resolver.can_view("restricted") is False
    assert resolver.can_edit("public_child") is False


def test_viewable_page_ids_filters_subtree():
    resolver = resolver_for("stranger", None)
    assert resolver.viewable_page_ids(list(PARENTS)) == ["root", "public_child"]


def test_cycle_in_tree_is_reported():
    resolver = WikiAccessResolver(
        parents={"a": "b", "b": "a"},
        restricted_page_ids=set(),
        user_permissions={},
        page_owners={},
        user_id="u1",
    )
    with pytest.raises(ValueError, match="Цикл"):
        _ = resolver.can_view("a")
