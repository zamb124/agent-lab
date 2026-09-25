"""Auto-generated migration.

Created: 2026-09-22 21:03:47
"""

depends_on = None


def upgrade(ctx):
    """Apply migration."""
    ctx.create_table(
        "secret_variables",
        fields=[
            {
                'name': 'secret_variable_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'company_id',
                'column_type': {
                    'kind': 'string',
                    'length': 100
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'variable_key',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'created_at',
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
            },
            {
                'name': 'version',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '1',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'secret',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'shared_for_execution',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'public',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'description',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'groups',
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
                'name': 'created_by',
                'column_type': {
                    'kind': 'string',
                    'length': 100
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'title',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'order_index',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'value_payload',
                'column_type': {
                    'kind': 'json_binary'
                },
                'db_type': 'JSONB',
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'value_encrypted',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': True,
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
                'name': 'secret_variables_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "secret_variable_versions",
        fields=[
            {
                'name': 'secret_variable_version_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'company_id',
                'column_type': {
                    'kind': 'string',
                    'length': 100
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'variable_key',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'version',
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
                'name': 'created_at',
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
            },
            {
                'name': 'secret',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'shared_for_execution',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'public',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'description',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'groups',
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
                'name': 'created_by',
                'column_type': {
                    'kind': 'string',
                    'length': 100
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'title',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'order_index',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'value_payload',
                'column_type': {
                    'kind': 'json_binary'
                },
                'db_type': 'JSONB',
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'value_encrypted',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': True,
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
                'name': 'secret_variable_versions_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_table("secret_variable_versions")
    ctx.drop_table("secret_variables")
