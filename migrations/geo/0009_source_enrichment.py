"""Geo: мультисорс-данные — обогащение адресов, правки админа, здания.

``geo_addresses`` получает ``source`` и enrich-колонки (``gar_guid``,
``canonical_name``, ``cadastral_number``); вечные (generation=0) строки
живут рядом с поколениями — чистка импорта их не трогает.

``geo_address_enrich`` — атрибуты от источников (ГАР, НСПД), ключ —
стабильный ``(osm_type, osm_id)``; ``geo_address_overrides`` — правки
админа (патч + тумбстоун + снапшот до-значений); ``geo_suppressions`` —
тумбстоуны прочих сущностей; ``geo_edge_overrides`` — закрытия дорог;
``geo_buildings`` — evergreen-контуры зданий (geom GENERATED из geojson).
``geo_manual_id_seq`` — отрицательные ``osm_id`` ручных адресов.
"""

depends_on = "0008_traffic_signals"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        """
        ALTER TABLE geo_addresses
            ADD COLUMN IF NOT EXISTS source varchar(32) NOT NULL DEFAULT 'osm',
            ADD COLUMN IF NOT EXISTS gar_guid varchar(36) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS canonical_name text NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS cadastral_number varchar(32) NOT NULL DEFAULT ''
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_addresses_gar_guid_idx "
        "ON geo_addresses (gar_guid) WHERE gar_guid <> ''"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_addresses_cadnum_idx "
        "ON geo_addresses (cadastral_number) WHERE cadastral_number <> ''"
    )

    ctx.execute("CREATE SEQUENCE IF NOT EXISTS geo_manual_id_seq")

    ctx.execute(
        "ALTER TABLE geo_enrich_queue "
        "ADD COLUMN IF NOT EXISTS run_after timestamptz"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_enrich_queue_claim_idx "
        "ON geo_enrich_queue (status, run_after)"
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_address_enrich (
            id bigserial PRIMARY KEY,
            osm_type varchar(16) NOT NULL,
            osm_id bigint NOT NULL,
            gar_guid varchar(36) NOT NULL DEFAULT '',
            canonical_name text NOT NULL DEFAULT '',
            cadastral_number varchar(32) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL,
            UNIQUE (osm_type, osm_id)
        )
        """
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_address_overrides (
            id bigserial PRIMARY KEY,
            osm_type varchar(16) NOT NULL,
            osm_id bigint NOT NULL,
            display_name text,
            city text,
            street text,
            housenumber text,
            postcode text,
            lat double precision,
            lng double precision,
            suppressed boolean NOT NULL DEFAULT false,
            reason text NOT NULL DEFAULT '',
            updated_by varchar(64) NOT NULL DEFAULT '',
            before jsonb,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            UNIQUE (osm_type, osm_id)
        )
        """
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_suppressions (
            id bigserial PRIMARY KEY,
            entity varchar(32) NOT NULL,
            osm_id bigint NOT NULL,
            reason text NOT NULL DEFAULT '',
            updated_by varchar(64) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL,
            UNIQUE (entity, osm_id)
        )
        """
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_edge_overrides (
            id bigserial PRIMARY KEY,
            osm_way_id bigint NOT NULL,
            cost_masks jsonb NOT NULL DEFAULT '{}'::jsonb,
            reason text NOT NULL DEFAULT '',
            updated_by varchar(64) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL,
            UNIQUE (osm_way_id)
        )
        """
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_buildings (
            id bigserial PRIMARY KEY,
            cadastral_number varchar(32) NOT NULL UNIQUE,
            address text NOT NULL DEFAULT '',
            lat double precision NOT NULL,
            lng double precision NOT NULL,
            geojson text NOT NULL DEFAULT '',
            geom geometry(Polygon,4326) GENERATED ALWAYS AS
                (ST_GeomFromGeoJSON(geojson)) STORED,
            region varchar(64) NOT NULL DEFAULT '',
            source varchar(32) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_buildings_geom_gist "
        "ON geo_buildings USING gist(geom)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP TABLE IF EXISTS geo_buildings")
    ctx.execute("DROP TABLE IF EXISTS geo_edge_overrides")
    ctx.execute("DROP TABLE IF EXISTS geo_suppressions")
    ctx.execute("DROP TABLE IF EXISTS geo_address_overrides")
    ctx.execute("DROP TABLE IF EXISTS geo_address_enrich")
    ctx.execute("DROP SEQUENCE IF EXISTS geo_manual_id_seq")
    ctx.execute(
        "ALTER TABLE geo_enrich_queue DROP COLUMN IF EXISTS run_after"
    )
    ctx.execute(
        """
        ALTER TABLE geo_addresses
            DROP COLUMN IF EXISTS source,
            DROP COLUMN IF EXISTS gar_guid,
            DROP COLUMN IF EXISTS canonical_name,
            DROP COLUMN IF EXISTS cadastral_number
        """
    )
