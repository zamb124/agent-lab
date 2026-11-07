"""Shop: ``shop_order_feedback`` — отзыв покупателя на выполненный заказ.

Один отзыв на заказ (``shop_order_id`` уникален); лента витрины —
``(shop_id, created_at DESC)``, рейтинг агрегируется в снапшоте.
"""

depends_on = "0019_shop_favorites"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_order_feedback ("
        "shop_order_feedback_id varchar(64) PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "shop_order_id varchar(64) NOT NULL, "
        "customer_id varchar(64) NOT NULL, "
        "customer_name varchar(200) NOT NULL DEFAULT '', "
        "rating integer NOT NULL, "
        "chips jsonb NOT NULL DEFAULT '[]', "
        "comment varchar(1000) NOT NULL DEFAULT '', "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS shop_order_feedback_order_uniq "
        "ON shop_order_feedback (shop_order_id)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_order_feedback_shop_created_idx "
        "ON shop_order_feedback (shop_id, created_at)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_order_feedback_customer_id_idx "
        "ON shop_order_feedback (customer_id)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP TABLE IF EXISTS shop_order_feedback")
