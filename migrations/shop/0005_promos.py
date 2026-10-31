"""Shop: акции — ShopPromo (condition+action+window) и скидки в заказе."""

depends_on = "0004_modifiers"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type("promo_stacking_enum", ["all", "exclusive"])
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_promos ("
        "shop_promo_id varchar(64) NOT NULL PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "name varchar(200) NOT NULL, "
        "is_active boolean NOT NULL DEFAULT true, "
        "sort integer NOT NULL DEFAULT 0, "
        "priority integer NOT NULL DEFAULT 0, "
        "stacking promo_stacking_enum NOT NULL DEFAULT 'all', "
        "active_window jsonb NOT NULL DEFAULT '{}'::jsonb, "
        "condition jsonb NOT NULL, "
        "action jsonb NOT NULL, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS ix_shop_promos_shop_active_sort "
        "ON shop_promos (shop_id, is_active, sort)"
    )
    ctx.execute(
        "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS discount_minor integer NOT NULL DEFAULT 0"
    )
    ctx.execute(
        "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS promos jsonb NOT NULL DEFAULT '[]'::jsonb"
    )
    ctx.execute(
        "ALTER TABLE shop_order_items "
        "ADD COLUMN IF NOT EXISTS discount_minor integer NOT NULL DEFAULT 0"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_order_items DROP COLUMN IF EXISTS discount_minor")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS promos")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS discount_minor")
    ctx.execute("DROP TABLE IF EXISTS shop_promos")
    ctx.execute("DROP TYPE IF EXISTS promo_stacking_enum")
