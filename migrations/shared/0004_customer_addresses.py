"""Shared: `customer_addresses` — сохранённые адреса покупателей (customers.mdc)."""

depends_on = "0003_create_customer_identity_provider_enum_enum"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_addresses (
            customer_address_id varchar(64) PRIMARY KEY,
            customer_id varchar(64) NOT NULL,
            label varchar(64) NOT NULL DEFAULT '',
            address varchar(500) NOT NULL DEFAULT '',
            lat double precision,
            lng double precision,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_used_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS customer_addresses_customer_id_idx "
        "ON customer_addresses (customer_id)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP INDEX IF EXISTS customer_addresses_customer_id_idx")
    ctx.execute("DROP TABLE IF EXISTS customer_addresses")
