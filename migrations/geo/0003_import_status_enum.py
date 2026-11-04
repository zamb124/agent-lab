"""Geo: ``status`` — enum вместо varchar, как в других сервисах.

Oxyde при UPDATE поля StrEnum кастует в ``geo_import_status_enum`` —
тип должен существовать в базе.
"""

depends_on = "0002_light_modes"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type(
        "geo_import_status_enum",
        ["idle", "downloading", "importing", "failed"],
    )
    ctx.execute("ALTER TABLE geo_import_state ALTER COLUMN status DROP DEFAULT")
    ctx.execute(
        "ALTER TABLE geo_import_state "
        "ALTER COLUMN status TYPE geo_import_status_enum USING status::geo_import_status_enum"
    )
    ctx.execute(
        "ALTER TABLE geo_import_state "
        "ALTER COLUMN status SET DEFAULT 'idle'::geo_import_status_enum"
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.execute(
        "ALTER TABLE geo_import_state "
        "ALTER COLUMN status TYPE varchar(32) USING status::varchar"
    )
    ctx.drop_enum_type("geo_import_status_enum")
