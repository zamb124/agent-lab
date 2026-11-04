"""Shop: pg_trgm GIN-индексы для поиска агрегатора и similar_by_name."""

depends_on = "0001_initial"


def upgrade(ctx):
    ctx.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_products_name_trgm_idx "
        "ON shop_products USING gin (name gin_trgm_ops)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_products_description_trgm_idx "
        "ON shop_products USING gin (description gin_trgm_ops)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_shops_name_trgm_idx "
        "ON shop_shops USING gin (name gin_trgm_ops)"
    )


def downgrade(ctx):
    ctx.execute("DROP INDEX IF EXISTS shop_products_name_trgm_idx")
    ctx.execute("DROP INDEX IF EXISTS shop_products_description_trgm_idx")
    ctx.execute("DROP INDEX IF EXISTS shop_shops_name_trgm_idx")
