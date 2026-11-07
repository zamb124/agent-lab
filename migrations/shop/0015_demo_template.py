"""Shop: ``demo_template`` — ключ сид-шаблона витрины.

``NULL`` — пользовательский магазин; непустое значение (`cafe`, `bakery`,
`pizza`, `market`) — витрина создана demo-seed при инициализации компании
или командой досева. Ключ нужен для идемпотентности сида и бейджа
«Пример» в списке магазинов.
"""

depends_on = "0014_customer_orders"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_shops ADD COLUMN IF NOT EXISTS demo_template VARCHAR(40)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_shops DROP COLUMN IF EXISTS demo_template")
