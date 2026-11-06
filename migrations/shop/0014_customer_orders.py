"""Shop: кабинет покупателя — сквозная история, таймлайн и гео-поля заказа.

`(customer_id, created_at)` — выборка `my/orders` по всем витринам;
`status_history` — журнал переходов для таймлайна; координаты и маршрут
фиксируются при создании (geo уже считает их в `_courier_route`).
"""

depends_on = "0013_delivery_eta"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_orders "
        "ADD COLUMN IF NOT EXISTS status_history JSONB NOT NULL DEFAULT '[]'"
    )
    ctx.execute(
        "UPDATE shop_orders SET status_history = jsonb_build_array("
        "jsonb_build_object('status', status::text, "
        "'at', coalesce(status_changed_at, created_at))) "
        "WHERE status_history = '[]'::jsonb"
    )
    ctx.execute(
        "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS delivery_lat double precision"
    )
    ctx.execute(
        "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS delivery_lng double precision"
    )
    ctx.execute(
        "ALTER TABLE shop_orders "
        "ADD COLUMN IF NOT EXISTS delivery_route JSONB NOT NULL DEFAULT '{}'"
    )
    ctx.execute(
        "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS shop_lat double precision"
    )
    ctx.execute(
        "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS shop_lng double precision"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_orders_customer_created_idx "
        "ON shop_orders (customer_id, created_at DESC)"
    )
    ctx.execute("DROP INDEX IF EXISTS shop_orders_customer_id_idx")


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_orders_customer_id_idx "
        "ON shop_orders (customer_id)"
    )
    ctx.execute("DROP INDEX IF EXISTS shop_orders_customer_created_idx")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS shop_lng")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS shop_lat")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS delivery_route")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS delivery_lng")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS delivery_lat")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS status_history")
