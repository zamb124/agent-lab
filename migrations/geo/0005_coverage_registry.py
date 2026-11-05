"""Geo: реестр покрытия — регионы, источники, статистика, курсоры, очередь.

``geo_regions`` — управление зоной покрытия (bbox + экстракты + enabled);
``geo_sources`` — allowlist открытых источников с лицензией; ``geo_stats``
— счётчики поколение×источник×регион×сущность; ``geo_source_cursors`` —
позиции resume чанковых импортов; ``geo_enrich_queue`` — задачи
обогащения для ``GEO_ENRICH_TICK``. Колонка ``region`` на данных помечает
строки импорта регионом-владельцем. ``geom`` регионов — GENERATED ALWAYS
``ST_MakeEnvelope``, в модели не объявлен.
"""

depends_on = "0004_edge_generation_uniq"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type("geo_region_kind_enum", ["city", "region", "custom"])
    ctx.create_enum_type(
        "geo_source_kind_enum",
        ["extract", "api", "registry", "telemetry", "manual"],
    )
    ctx.create_enum_type(
        "geo_cursor_status_enum", ["idle", "running", "done", "failed"]
    )
    ctx.create_enum_type(
        "geo_enrich_status_enum", ["pending", "running", "done", "failed"]
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_regions (
            id bigserial PRIMARY KEY,
            name varchar(64) NOT NULL UNIQUE,
            title varchar(255) NOT NULL DEFAULT '',
            kind geo_region_kind_enum NOT NULL DEFAULT 'custom',
            bbox_south double precision NOT NULL,
            bbox_west double precision NOT NULL,
            bbox_north double precision NOT NULL,
            bbox_east double precision NOT NULL,
            extract_urls jsonb NOT NULL DEFAULT '[]'::jsonb,
            replication_url text NOT NULL DEFAULT '',
            enabled boolean NOT NULL DEFAULT true,
            last_imported_at timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            geom geometry(Polygon,4326) GENERATED ALWAYS AS
                (ST_MakeEnvelope(bbox_west, bbox_south, bbox_east, bbox_north, 4326)) STORED
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_regions_geom_gist ON geo_regions USING gist(geom)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_regions_enabled_idx ON geo_regions (enabled)"
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_sources (
            id bigserial PRIMARY KEY,
            name varchar(64) NOT NULL UNIQUE,
            title varchar(255) NOT NULL DEFAULT '',
            kind geo_source_kind_enum NOT NULL DEFAULT 'extract',
            license varchar(255) NOT NULL DEFAULT '',
            attribution text NOT NULL DEFAULT '',
            url text NOT NULL DEFAULT '',
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
        """
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_stats (
            id bigserial PRIMARY KEY,
            generation integer NOT NULL DEFAULT 0,
            source varchar(64) NOT NULL,
            region varchar(64) NOT NULL DEFAULT '',
            entity varchar(64) NOT NULL,
            rows bigint NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL,
            UNIQUE (generation, source, region, entity)
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_stats_generation_idx ON geo_stats (generation)"
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_source_cursors (
            id bigserial PRIMARY KEY,
            source varchar(64) NOT NULL,
            region varchar(64) NOT NULL DEFAULT '',
            cursor text NOT NULL DEFAULT '',
            status geo_cursor_status_enum NOT NULL DEFAULT 'idle',
            rows_done bigint NOT NULL DEFAULT 0,
            last_error text NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL,
            UNIQUE (source, region)
        )
        """
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_enrich_queue (
            id bigserial PRIMARY KEY,
            kind varchar(64) NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            priority integer NOT NULL DEFAULT 0,
            status geo_enrich_status_enum NOT NULL DEFAULT 'pending',
            attempts integer NOT NULL DEFAULT 0,
            last_error text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            done_at timestamptz
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_enrich_queue_status_idx "
        "ON geo_enrich_queue (status, priority)"
    )

    ctx.execute(
        "ALTER TABLE geo_addresses "
        "ADD COLUMN IF NOT EXISTS region varchar(64) NOT NULL DEFAULT ''"
    )
    ctx.execute(
        "ALTER TABLE geo_road_vertices "
        "ADD COLUMN IF NOT EXISTS region varchar(64) NOT NULL DEFAULT ''"
    )
    ctx.execute(
        "ALTER TABLE geo_road_edges "
        "ADD COLUMN IF NOT EXISTS region varchar(64) NOT NULL DEFAULT ''"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE geo_road_edges DROP COLUMN IF EXISTS region")
    ctx.execute("ALTER TABLE geo_road_vertices DROP COLUMN IF EXISTS region")
    ctx.execute("ALTER TABLE geo_addresses DROP COLUMN IF EXISTS region")
    ctx.execute("DROP TABLE IF EXISTS geo_enrich_queue")
    ctx.execute("DROP TABLE IF EXISTS geo_source_cursors")
    ctx.execute("DROP TABLE IF EXISTS geo_stats")
    ctx.execute("DROP TABLE IF EXISTS geo_sources")
    ctx.execute("DROP TABLE IF EXISTS geo_regions")
    ctx.drop_enum_type("geo_enrich_status_enum")
    ctx.drop_enum_type("geo_cursor_status_enum")
    ctx.drop_enum_type("geo_source_kind_enum")
    ctx.drop_enum_type("geo_region_kind_enum")
