"""Shop: ``shop_favorites`` — избранные товары покупателя на витрине.

Персональная витрина: id'шники резолвит ``/personal`` для авторизованного
покупателя; анонимный снапшот избранное не несёт.
"""

depends_on = "0018_delivery_checkout"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TYPE shop_shelf_kind_enum ADD VALUE IF NOT EXISTS 'favorites'"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_favorites ("
        "shop_favorite_id varchar(64) PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "product_id varchar(64) NOT NULL, "
        "customer_id varchar(64) NOT NULL, "
        "created_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_favorites_shop_customer_idx "
        "ON shop_favorites (shop_id, customer_id)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_favorites_customer_id_idx "
        "ON shop_favorites (customer_id)"
    )
    ctx.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS shop_favorites_product_customer_uniq "
        "ON shop_favorites (product_id, customer_id)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP TABLE IF EXISTS shop_favorites")
