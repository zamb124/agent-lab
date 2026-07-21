"""Local Google Sheets/Docs/Drive/token HTTP emulator for strict integration tests."""

from tests.fixtures.google_api_emulator.handle import (
    GoogleApiEmulatorHandle,
    apply_google_api_bases,
    google_api_emulator,
    make_emulator_service_account_json,
)

__all__ = [
    "GoogleApiEmulatorHandle",
    "apply_google_api_bases",
    "google_api_emulator",
    "make_emulator_service_account_json",
]
