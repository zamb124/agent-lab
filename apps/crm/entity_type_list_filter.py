"""
Пара (entity_type, entity_subtype) для фильтрации списка сущностей по строке справочника entity_types.

Семантика совпадает с тем, как типы ветки note попадают в колонки CRMEntity после
EntityService._resolve_storage_type_for_note_family: потомки note в БД имеют
entity_type=note и entity_subtype=<type_id листа>. Остальные типы фильтруются по
entity_type=<type_id>, entity_subtype отсутствует.

parent_by_type_id: для каждого type_id из строк типов компании значение parent_type_id (или None у корня).
Ссылки на системные корни ``note``/``task`` разрешаются даже если строка корня отсутствует в таблице (частичный справочник).
"""

from typing import Mapping, Optional

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID


def resolve_list_entity_query_pair(
    leaf_type_id: str,
    parent_by_type_id: Mapping[str, Optional[str]],
) -> tuple[str, Optional[str]]:
    if not leaf_type_id:
        raise ValueError("leaf_type_id must be non-empty")
    if leaf_type_id not in parent_by_type_id:
        raise ValueError(f"entity type not in parent map: {leaf_type_id}")

    if leaf_type_id == NOTE_ROOT_ENTITY_TYPE_ID:
        return (NOTE_ROOT_ENTITY_TYPE_ID, None)
    if leaf_type_id == TASK_ROOT_ENTITY_TYPE_ID:
        return (TASK_ROOT_ENTITY_TYPE_ID, None)

    seen: set[str] = set()
    cur: Optional[str] = leaf_type_id
    while cur is not None:
        if cur in seen:
            raise ValueError(f"cycle in entity type parent chain near {cur}")
        seen.add(cur)
        if cur == NOTE_ROOT_ENTITY_TYPE_ID:
            return (NOTE_ROOT_ENTITY_TYPE_ID, leaf_type_id)
        if cur == TASK_ROOT_ENTITY_TYPE_ID:
            return (TASK_ROOT_ENTITY_TYPE_ID, leaf_type_id)
        cur = parent_by_type_id[cur]
        if cur is not None and cur not in parent_by_type_id:
            if cur == NOTE_ROOT_ENTITY_TYPE_ID:
                return (NOTE_ROOT_ENTITY_TYPE_ID, leaf_type_id)
            if cur == TASK_ROOT_ENTITY_TYPE_ID:
                return (TASK_ROOT_ENTITY_TYPE_ID, leaf_type_id)
            raise ValueError(f"parent type not in map: {cur}")

    return (leaf_type_id, None)
