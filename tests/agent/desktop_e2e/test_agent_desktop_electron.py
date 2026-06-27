"""Desktop E2E: launch собранного HumanitecAgent."""

from __future__ import annotations

from tests.agent.desktop_e2e.desktop_app import is_placeholder_artifact


def test_d4_first_launch_electron_smoke(
    humanitec_desktop_release_artifact: str,
    humanitec_desktop_process_factory,
) -> None:
    artifact_path = __import__("pathlib").Path(humanitec_desktop_release_artifact)
    assert artifact_path.is_file()
    assert not is_placeholder_artifact(artifact_path)

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
    finally:
        desktop.stop()
