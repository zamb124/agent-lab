"""Shared: ``files_catalog_required_chk`` — ``stock_entity`` в source_kind без Docs-каталога.

Файлы складских сущностей (фото исключений ТСД) освобождены от размещения
в Documents (``DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS``), значит ``catalog_id``
остаётся NULL. CHECK из 0001 разрешал NULL только для ``''``,
``generated_ephemeral`` и ``platform_auxiliary`` — регистрация файла
падала constraint violation.
"""

depends_on = "0009_user_badges"

_CATALOG_CHECK = "ALTER TABLE files ADD CONSTRAINT files_catalog_required_chk CHECK "
_CATALOG_CHECK_TAIL = (
    "((catalog_id IS NULL) = (source_kind = ANY (ARRAY[{kinds}]::text[])))"
)


def upgrade(ctx):
    """Apply migration."""
    ctx.execute("ALTER TABLE files DROP CONSTRAINT IF EXISTS files_catalog_required_chk")
    kinds = "'', 'generated_ephemeral', 'platform_auxiliary', 'stock_entity'"
    ctx.execute(_CATALOG_CHECK + _CATALOG_CHECK_TAIL.format(kinds=kinds))


def downgrade(ctx):
    """Revert migration."""
    ctx.execute("ALTER TABLE files DROP CONSTRAINT IF EXISTS files_catalog_required_chk")
    kinds = "'', 'generated_ephemeral', 'platform_auxiliary'"
    ctx.execute(_CATALOG_CHECK + _CATALOG_CHECK_TAIL.format(kinds=kinds))
