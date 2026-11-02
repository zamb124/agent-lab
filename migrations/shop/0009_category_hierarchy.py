"""Shop: иерархия категорий — parent_id, sort внутри siblings."""

depends_on = "0008_shop_badges"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_categories "
        "ADD COLUMN IF NOT EXISTS parent_id varchar(64) NULL"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_categories_shop_parent_sort "
        "ON shop_categories (shop_id, parent_id, sort)"
    )
    ctx.execute("DROP INDEX IF EXISTS shop_categories_shop_id_sort_idx")


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP INDEX IF EXISTS shop_categories_shop_parent_sort")
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_categories_shop_id_sort_idx "
        "ON shop_categories (shop_id, sort)"
    )
    ctx.execute("ALTER TABLE shop_categories DROP COLUMN IF EXISTS parent_id")
