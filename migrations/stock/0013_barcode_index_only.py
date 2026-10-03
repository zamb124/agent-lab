"""Единый источник штрихкодов — только ``stock_barcodes``.

До этой миграции коды жили дважды: колонкой ``barcode`` на самой
сущности (product/location/lot/packaging/resource/transfer) и строкой
индекса ``stock_barcodes``. Двойная запись могла рассинхронизироваться
(колонка есть — записи в индексе нет → скан не резолвится) и держала
шесть поисковых путей вместо одного.

Теперь индекс — единственная точка истины: один код = один носитель
(`unique (company_id, barcode)`), скан идёт в одну таблицу, у сущности
может быть несколько кодов (предел «одного поля» снят). Побочный
выигрыш: коды накладных (``entity_type='transfer'``) наконец резолвятся —
раньше колонка ``stock_transfers.barcode`` писалась, но в индекс не
попадала, и отсканировать документ было нельзя.

Upgrade безпотерьный: перед удалением колонок все значения копируются
в ``stock_barcodes`` (включая накладные — они получают
``entity_type='transfer'`` и впервые начинают резолвиться).
Downgrade восстанавливает колонки и заливает их обратно из индекса.
"""

depends_on = "0012_drop_stock_route_steps_table"

# (таблица, pk-колонка, entity_type)
_SOURCES = (
    ("stock_products", "product_id", "product"),
    ("stock_product_packagings", "packaging_id", "packaging"),
    ("stock_locations", "location_id", None),  # container vs location: по usage
    ("stock_lots", "lot_id", "lot"),
    ("stock_resources", "resource_id", "resource"),
    ("stock_transfers", "transfer_id", "transfer"),
)


def upgrade(ctx):
    """Backfill → индекс, затем снять шесть колонок и их индексов."""
    for table, pk, entity_type in _SOURCES:
        if entity_type is None:
            # Локации делятся на два типа носителей по usage=container.
            ctx.execute(
                f"INSERT INTO stock_barcodes"
                f" (barcode_id, company_id, barcode, entity_type, entity_id, created_at)"
                f" SELECT 'bcm_' || md5(t.company_id || ':' || t.barcode),"
                f" t.company_id, t.barcode,"
                f" (CASE WHEN t.usage = 'container' THEN 'container'"
                f" ELSE 'location' END)::stock_barcode_entity_type_enum,"
                f" t.{pk}, now() FROM {table} t"
                f" WHERE t.barcode IS NOT NULL AND btrim(t.barcode) <> ''"
                f" AND NOT EXISTS (SELECT 1 FROM stock_barcodes b"
                f" WHERE b.company_id = t.company_id AND b.barcode = t.barcode)"
            )
        else:
            ctx.execute(
                f"INSERT INTO stock_barcodes"
                f" (barcode_id, company_id, barcode, entity_type, entity_id, created_at)"
                f" SELECT 'bcm_' || md5(t.company_id || ':' || t.barcode),"
                f" t.company_id, t.barcode,"
                f" '{entity_type}'::stock_barcode_entity_type_enum, t.{pk}, now()"
                f" FROM {table} t"
                f" WHERE t.barcode IS NOT NULL AND btrim(t.barcode) <> ''"
                f" AND NOT EXISTS (SELECT 1 FROM stock_barcodes b"
                f" WHERE b.company_id = t.company_id AND b.barcode = t.barcode)"
            )
    ctx.drop_index("stock_locations", "stock_locations_company_id_barcode_idx")
    ctx.drop_index("stock_lots", "stock_lots_company_id_barcode_idx")
    ctx.drop_index("stock_product_packagings", "stock_product_packagings_company_id_barcode_idx")
    ctx.drop_index("stock_products", "stock_products_company_id_barcode_idx")
    ctx.drop_index("stock_resources", "stock_resources_company_id_barcode_idx")
    ctx.drop_index("stock_transfers", "stock_transfers_company_id_barcode_idx")
    ctx.drop_column("stock_locations", "barcode")
    ctx.drop_column("stock_lots", "barcode")
    ctx.drop_column("stock_product_packagings", "barcode")
    ctx.drop_column("stock_products", "barcode")
    ctx.drop_column("stock_resources", "barcode")
    ctx.alter_column("stock_routes", "steps", default=None)
    ctx.drop_column("stock_transfers", "barcode")


def downgrade(ctx):
    """Вернуть колонки, залить их из индекса, вернуть индексы поиска."""
    for table, pk, entity_type in _SOURCES:
        ctx.add_column(table, {
            'name': 'barcode',
            'column_type': {'kind': 'string', 'length': 128},
            'db_type': None,
            'nullable': True,
            'primary_key': False,
            'unique': False,
            'default': None,
            'auto_increment': False,
            'max_length': 128,
            'max_digits': None,
            'decimal_places': None,
        })
        if entity_type is None:
            ctx.execute(
                f"UPDATE {table} t SET barcode = ("
                f" SELECT b.barcode FROM stock_barcodes b"
                f" WHERE b.company_id = t.company_id"
                f" AND b.entity_type IN ('location', 'container')"
                f" AND b.entity_id = t.{pk} LIMIT 1)"
            )
        else:
            ctx.execute(
                f"UPDATE {table} t SET barcode = ("
                f" SELECT b.barcode FROM stock_barcodes b"
                f" WHERE b.company_id = t.company_id"
                f" AND b.entity_type = '{entity_type}'"
                f" AND b.entity_id = t.{pk} LIMIT 1)"
            )
    ctx.create_index("stock_transfers", {
        'name': 'stock_transfers_company_id_barcode_idx',
        'fields': ['company_id', 'barcode'],
        'unique': False,
        'method': None,
    })
    ctx.create_index("stock_resources", {
        'name': 'stock_resources_company_id_barcode_idx',
        'fields': ['company_id', 'barcode'],
        'unique': False,
        'method': None,
    })
    ctx.create_index("stock_products", {
        'name': 'stock_products_company_id_barcode_idx',
        'fields': ['company_id', 'barcode'],
        'unique': False,
        'method': None,
    })
    ctx.create_index("stock_product_packagings", {
        'name': 'stock_product_packagings_company_id_barcode_idx',
        'fields': ['company_id', 'barcode'],
        'unique': False,
        'method': None,
    })
    ctx.create_index("stock_lots", {
        'name': 'stock_lots_company_id_barcode_idx',
        'fields': ['company_id', 'barcode'],
        'unique': False,
        'method': None,
    })
    ctx.create_index("stock_locations", {
        'name': 'stock_locations_company_id_barcode_idx',
        'fields': ['company_id', 'barcode'],
        'unique': False,
        'method': None,
    })
