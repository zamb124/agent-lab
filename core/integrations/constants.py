"""Канон коннекторов на integration_credentials (без per-vendor таблиц)."""

from typing import Final

# Sentinel user_id для company-owned credentials (SA и аналоги).
COMPANY_INTEGRATION_USER_ID: Final[str] = "__company__"

TOKEN_TYPE_SERVICE_ACCOUNT: Final[str] = "service_account"

# metadata keys для company SA credentials
METADATA_IMPERSONATE_EMAIL: Final[str] = "impersonate_email"
