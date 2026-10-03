"""Источник релизов LinnexAgent читается из Settings, не из os.environ."""

from apps.agent.local_releases import release_source
from core.config import get_settings


def test_release_source_explicit_value_wins_over_testing() -> None:
    settings = get_settings()
    saved_source = settings.agent.releases.source
    saved_testing = settings.testing
    try:
        settings.agent.releases.source = "github"
        settings.testing = True
        assert release_source() == "github"
        settings.agent.releases.source = "local"
        assert release_source() == "local"
    finally:
        settings.agent.releases.source = saved_source
        settings.testing = saved_testing


def test_release_source_empty_uses_testing_flag() -> None:
    settings = get_settings()
    saved_source = settings.agent.releases.source
    saved_testing = settings.testing
    try:
        settings.agent.releases.source = ""
        settings.testing = True
        assert release_source() == "local"
        settings.testing = False
        assert release_source() == "github"
    finally:
        settings.agent.releases.source = saved_source
        settings.testing = saved_testing
