"""Shop: модификаторы — reusable группы опций, связь с продуктами, снапшот в заказе."""

depends_on = "0003_telegram"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('modifier_group_kind_enum', ['addon', 'remove'])
    ctx.create_enum_type('modifier_selection_mode_enum', ['single', 'multi'])
    ctx.create_enum_type('modifier_price_mode_enum', ['delta', 'absolute'])
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_modifier_groups ("
        "shop_modifier_group_id varchar(64) NOT NULL PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "name varchar(200) NOT NULL, "
        "description varchar(500) NOT NULL DEFAULT '', "
        "kind modifier_group_kind_enum NOT NULL DEFAULT 'addon', "
        "selection_mode modifier_selection_mode_enum NOT NULL DEFAULT 'multi', "
        "min_selected integer NOT NULL DEFAULT 0, "
        "max_selected integer NULL, "
        "price_mode modifier_price_mode_enum NOT NULL DEFAULT 'delta', "
        "is_active boolean NOT NULL DEFAULT true, "
        "sort integer NOT NULL DEFAULT 0, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_modifier_groups_shop_sort "
        "ON shop_modifier_groups (shop_id, sort)"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_modifier_options ("
        "shop_modifier_option_id varchar(64) NOT NULL PRIMARY KEY, "
        "group_id varchar(64) NOT NULL, "
        "name varchar(200) NOT NULL, "
        "price_minor integer NOT NULL DEFAULT 0, "
        "is_default boolean NOT NULL DEFAULT false, "
        "is_available boolean NOT NULL DEFAULT true, "
        "max_per_option integer NOT NULL DEFAULT 1, "
        "nested_group_id varchar(64) NULL, "
        "external_id varchar(128) NULL, "
        "sort integer NOT NULL DEFAULT 0, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_modifier_options_group_sort "
        "ON shop_modifier_options (group_id, sort)"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_product_modifier_groups ("
        "product_id varchar(64) NOT NULL, "
        "group_id varchar(64) NOT NULL, "
        "sort integer NOT NULL DEFAULT 0, "
        "min_selected integer NULL, "
        "max_selected integer NULL, "
        "PRIMARY KEY (product_id, group_id))"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_product_modifier_groups_product_sort "
        "ON shop_product_modifier_groups (product_id, sort)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_product_modifier_groups_group "
        "ON shop_product_modifier_groups (group_id)"
    )
    ctx.execute(
        "ALTER TABLE shop_order_items "
        "ADD COLUMN IF NOT EXISTS modifiers jsonb NOT NULL DEFAULT '[]'"
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.execute("ALTER TABLE shop_order_items DROP COLUMN IF EXISTS modifiers")
    ctx.execute("DROP TABLE IF EXISTS shop_product_modifier_groups")
    ctx.execute("DROP TABLE IF EXISTS shop_modifier_options")
    ctx.execute("DROP TABLE IF EXISTS shop_modifier_groups")
    ctx.execute("DROP TYPE IF EXISTS modifier_price_mode_enum")
    ctx.execute("DROP TYPE IF EXISTS modifier_selection_mode_enum")
    ctx.execute("DROP TYPE IF EXISTS modifier_group_kind_enum")
