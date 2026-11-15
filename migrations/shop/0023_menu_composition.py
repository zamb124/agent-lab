"""Состав и аллергены листинга витрины.

Черновик импорта меню живёт в Redis и в таблицу не пишется.
Поля появляются на ``shop_products`` и уходят в карточку витрины.
"""

depends_on = "0022_product_facet"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_products "
        "ADD COLUMN IF NOT EXISTS ingredients jsonb NOT NULL DEFAULT '[]'"
    )
    ctx.execute(
        "ALTER TABLE shop_products "
        "ADD COLUMN IF NOT EXISTS allergens jsonb NOT NULL DEFAULT '[]'"
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.execute("ALTER TABLE shop_products DROP COLUMN IF EXISTS allergens")
    ctx.execute("ALTER TABLE shop_products DROP COLUMN IF EXISTS ingredients")
