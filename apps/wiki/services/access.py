"""
Права доступа к страницам wiki.

Три оси, все навешиваются на страницу:

* namespace — участник компании с доступом к пространству читает и правит
  любую страницу, на которой нет ограничений. Это состояние по умолчанию;
* участники (`wiki_page_members`) — ограничение, поставленное на страницу,
  наследуется всему поддереву по `parent_page_id`;
* публичная ссылка — анонимный просмотр по токену.

Видимость (`WikiVisibility`) выводится отсюда и нигде больше: именно она
решает, в какой RAG-namespace попадёт страница, поэтому второй источник
истины означал бы утечку приватного текста в общий поиск.
"""

from __future__ import annotations

from apps.wiki.models.domain import WikiPagePermission, WikiVisibility

_WRITE_PERMISSIONS: frozenset[WikiPagePermission] = frozenset(
    {WikiPagePermission.WRITE, WikiPagePermission.ADMIN}
)


class WikiAccessResolver:
    """Расчёт доступа по срезу дерева namespace.

    Строится один раз на запрос: обход предков для каждой страницы по
    отдельности превратил бы список дерева в лавину запросов.
    """

    def __init__(
        self,
        parents: dict[str, str | None],
        restricted_page_ids: set[str],
        user_permissions: dict[str, WikiPagePermission],
        page_owners: dict[str, str],
        user_id: str | None,
    ) -> None:
        self._parents: dict[str, str | None] = parents
        self._restricted_page_ids: set[str] = restricted_page_ids
        self._user_permissions: dict[str, WikiPagePermission] = user_permissions
        self._page_owners: dict[str, str] = page_owners
        self._user_id: str | None = user_id

    def _chain(self, wiki_page_id: str) -> list[str]:
        """Страница и её предки, от самой страницы к корню."""
        chain: list[str] = []
        current: str | None = wiki_page_id
        seen: set[str] = set()
        while current is not None:
            if current in seen:
                raise ValueError(f"Цикл в дереве wiki на странице {current}")
            seen.add(current)
            chain.append(current)
            current = self._parents.get(current)
        return chain

    def nearest_restriction(self, wiki_page_id: str) -> str | None:
        """Ближайшая страница вверх по дереву, на которой стоит ограничение."""
        for page_id in self._chain(wiki_page_id):
            if page_id in self._restricted_page_ids:
                return page_id
        return None

    def visibility(self, wiki_page_id: str) -> WikiVisibility:
        if self.nearest_restriction(wiki_page_id) is None:
            return WikiVisibility.COMPANY
        return WikiVisibility.RESTRICTED

    def can_view(self, wiki_page_id: str) -> bool:
        if self.nearest_restriction(wiki_page_id) is None:
            return True
        if self._user_id is None:
            return False
        if self._page_owners.get(wiki_page_id) == self._user_id:
            return True
        return any(page_id in self._user_permissions for page_id in self._chain(wiki_page_id))

    def can_edit(self, wiki_page_id: str) -> bool:
        if self._user_id is None:
            return False
        if self._page_owners.get(wiki_page_id) == self._user_id:
            return True
        if self.nearest_restriction(wiki_page_id) is None:
            return True
        for page_id in self._chain(wiki_page_id):
            permission = self._user_permissions.get(page_id)
            if permission is not None:
                return permission in _WRITE_PERMISSIONS
        return False

    def can_administer(self, wiki_page_id: str) -> bool:
        """Право менять доступ и удалять страницу."""
        if self._user_id is None:
            return False
        if self._page_owners.get(wiki_page_id) == self._user_id:
            return True
        for page_id in self._chain(wiki_page_id):
            permission = self._user_permissions.get(page_id)
            if permission is not None:
                return permission == WikiPagePermission.ADMIN
        return self.nearest_restriction(wiki_page_id) is None

    def viewable_page_ids(self, candidates: list[str]) -> list[str]:
        return [page_id for page_id in candidates if self.can_view(page_id)]

    def visibility_map(self, candidates: list[str]) -> dict[str, WikiVisibility]:
        return {page_id: self.visibility(page_id) for page_id in candidates}


__all__ = ["WikiAccessResolver"]
