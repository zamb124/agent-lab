"""Geo: состояние импорта ГАР — в Postgres вместо памяти воркера.

``geo_gar_addr_objects`` — справочник имён адресообразующих объектов
региона (AS_ADDR_OBJ); ``geo_gar_houses`` — дома с materialized PATH
(AS_HOUSES + AS_ADM_HIERARCHY). Обе таблицы — персистентное состояние
для инкрементальных дельт, заменяют ``state_{region}.json`` и
in-memory dict'ы разбора: парсер льёт строки чанками, матч идёт
keyset-страницами — пиковая память не зависит от размера выгрузки.
``version`` дома — версия архива, последним тронувшая строку: область
матча и признак протухания при полном реимпорте.

Частичный индекс очереди обогащения — дедуп ``gar_objectid`` при
массовой раскладке промахов (INSERT ... WHERE NOT IN).
"""

depends_on = "0009_source_enrichment"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_gar_addr_objects (
            id bigserial PRIMARY KEY,
            region varchar(64) NOT NULL,
            object_id bigint NOT NULL,
            name text NOT NULL DEFAULT '',
            UNIQUE (region, object_id)
        )
        """
    )
    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_gar_houses (
            id bigserial PRIMARY KEY,
            region varchar(64) NOT NULL,
            object_id bigint NOT NULL,
            guid varchar(36) NOT NULL DEFAULT '',
            housenum text NOT NULL DEFAULT '',
            addnum1 text NOT NULL DEFAULT '',
            addnum2 text NOT NULL DEFAULT '',
            path text NOT NULL DEFAULT '',
            active boolean NOT NULL DEFAULT true,
            version bigint NOT NULL DEFAULT 0,
            UNIQUE (region, object_id)
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_enrich_queue_gar_objectid_idx "
        "ON geo_enrich_queue ((payload->>'gar_objectid')) "
        "WHERE kind = 'gar_unresolved' AND status IN ('pending','running')"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP INDEX IF EXISTS geo_enrich_queue_gar_objectid_idx")
    ctx.execute("DROP TABLE IF EXISTS geo_gar_houses")
    ctx.execute("DROP TABLE IF EXISTS geo_gar_addr_objects")
