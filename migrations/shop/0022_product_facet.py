"""Shop: shop_products → фасет витрины поверх catalog_products.

Общий контент (name/description/photo) уезжает в shared-каталог;
``product_id`` — канонический id товара. Связки модификаторов
становятся shop-scoped (PK с shop_id). Добавляется проекция
``shop_market_items`` для trgm-поиска агрегатора. Данные листинга
сбрасываются — пересеиваются демо-сидом.
"""

depends_on = "0021_loyalty"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute("DROP INDEX IF EXISTS shop_products_name_trgm_idx")
    ctx.execute("DROP INDEX IF EXISTS shop_products_description_trgm_idx")
    ctx.execute("DELETE FROM shop_favorites")
    ctx.execute("DELETE FROM shop_back_in_stock")
    ctx.execute("DELETE FROM shop_shelves")
    ctx.execute("DELETE FROM shop_products")
    ctx.drop_table("shop_product_modifier_groups")
    ctx.add_column("shop_products", {
    'name': 'product_id',
    'column_type': {
        'kind': 'string',
        'length': 64
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': 64,
    'max_digits': None,
    'decimal_places': None
})
    ctx.drop_column("shop_products", "name")
    ctx.drop_column("shop_products", "description")
    ctx.drop_column("shop_products", "photo_file_id")
    ctx.create_index("shop_products", {
    'name': 'shop_products_shop_id_product_id_idx',
    'fields': [
        'shop_id',
        'product_id'
    ],
    'unique': True,
    'method': None
})
    ctx.create_index("shop_products", {
    'name': 'shop_products_product_id_idx',
    'fields': [
        'product_id'
    ],
    'unique': False,
    'method': None
})
    ctx.execute(
        "CREATE TABLE shop_product_modifier_groups ("
        "shop_id varchar(64) NOT NULL, "
        "product_id varchar(64) NOT NULL, "
        "group_id varchar(64) NOT NULL, "
        "sort bigint NOT NULL DEFAULT 0, "
        "min_selected bigint NULL, "
        "max_selected bigint NULL, "
        "PRIMARY KEY (shop_id, product_id, group_id))"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_product_modifier_groups_shop_id_product_id_sort_idx "
        "ON shop_product_modifier_groups (shop_id, product_id, sort)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_product_modifier_groups_group_id_idx "
        "ON shop_product_modifier_groups (group_id)"
    )
    ctx.create_table(
        "shop_market_items",
        fields=[
            {
                'name': 'shop_market_item_id',
                'column_type': {
                    'kind': 'string',
                    'length': 128
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 128,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'shop_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'product_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'name',
                'column_type': {
                    'kind': 'string',
                    'length': 300
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 300,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'description',
                'column_type': {
                    'kind': 'string',
                    'length': 1000
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 1000,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'portion',
                'column_type': {
                    'kind': 'string',
                    'length': 50
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 50,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'badges',
                'column_type': {
                    'kind': 'json_binary'
                },
                'db_type': 'JSONB',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'price_minor',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'photo_file_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'updated_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            }
        ],
        indexes=[
            {
                'name': 'shop_market_items_shop_id_product_id_idx',
                'fields': [
                    'shop_id',
                    'product_id'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'shop_market_items_product_id_idx',
                'fields': [
                    'product_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_market_items_name_trgm_idx "
        "ON shop_market_items USING gin (name gin_trgm_ops)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_market_items_description_trgm_idx "
        "ON shop_market_items USING gin (description gin_trgm_ops)"
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.execute("DROP INDEX IF EXISTS shop_market_items_name_trgm_idx")
    ctx.execute("DROP INDEX IF EXISTS shop_market_items_description_trgm_idx")
    ctx.drop_table("shop_market_items")
    ctx.drop_table("shop_product_modifier_groups")
    ctx.drop_index("shop_products", "shop_products_product_id_idx")
    ctx.drop_index("shop_products", "shop_products_shop_id_product_id_idx")
    ctx.drop_column("shop_products", "product_id")
    ctx.add_column("shop_products", {
    'name': 'photo_file_id',
    'column_type': {
        'kind': 'string',
        'length': 64
    },
    'db_type': None,
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': 64,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("shop_products", {
    'name': 'description',
    'column_type': {
        'kind': 'string',
        'length': 1000
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "''",
    'auto_increment': False,
    'max_length': 1000,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("shop_products", {
    'name': 'name',
    'column_type': {
        'kind': 'string',
        'length': 300
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "''",
    'auto_increment': False,
    'max_length': 300,
    'max_digits': None,
    'decimal_places': None
})
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_products_name_trgm_idx "
        "ON shop_products USING gin (name gin_trgm_ops)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_products_description_trgm_idx "
        "ON shop_products USING gin (description gin_trgm_ops)"
    )
    ctx.execute(
        "CREATE TABLE shop_product_modifier_groups ("
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
        "CREATE INDEX IF NOT EXISTS shop_product_modifier_groups_group_idx "
        "ON shop_product_modifier_groups (group_id)"
    )
