"""Метка deployment.environment берётся из Settings, не из PLATFORM_ENV."""

from core.logging.setup import log_deployment_environment


def test_testing_contour_is_test() -> None:
    assert (
        log_deployment_environment(
            testing=True,
            server_env="production",
            deployment_version="abc",
        )
        == "test"
    )


def test_deployment_version_is_production() -> None:
    assert (
        log_deployment_environment(
            testing=False,
            server_env="development",
            deployment_version="sha",
        )
        == "production"
    )


def test_server_env_test_without_release() -> None:
    assert (
        log_deployment_environment(
            testing=False,
            server_env="test",
            deployment_version=None,
        )
        == "test"
    )


def test_development_without_release_is_local() -> None:
    assert (
        log_deployment_environment(
            testing=False,
            server_env="development",
            deployment_version=None,
        )
        == "local"
    )


def test_default_production_without_release_is_local() -> None:
    assert (
        log_deployment_environment(
            testing=False,
            server_env="production",
            deployment_version="  ",
        )
        == "local"
    )
