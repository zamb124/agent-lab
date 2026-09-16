from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models.node_config import GraphNodeConfig


def test_code_agent_git_url_without_sha_saves() -> None:
    node = GraphNodeConfig.model_validate(
        {
            "type": "code_agent",
            "name": "code_agent",
            "language": "python",
            "invoke_kind": "cli",
            "catalog_id": "7fcd19ba590c40fba4e09fc9347a6f5a",
            "git_url": "https://github.com/zub123123123/cheetah-agent.git",
            "source_sha": "",
        }
    )
    assert node.git_url == "https://github.com/zub123123123/cheetah-agent.git"
    assert node.source_sha is None


def test_code_agent_source_sha_requires_git_url() -> None:
    with pytest.raises(ValidationError, match="source_sha requires git_url"):
        GraphNodeConfig.model_validate(
            {
                "type": "code_agent",
                "language": "python",
                "source_sha": "70eb6c3c6909d1f975d9c7e6c723bae5db897478",
            }
        )


def test_code_agent_source_sha_must_be_40_hex() -> None:
    with pytest.raises(ValidationError, match="source_sha must be 40 hex"):
        GraphNodeConfig.model_validate(
            {
                "type": "code_agent",
                "language": "python",
                "git_url": "https://github.com/zub123123123/cheetah-agent.git",
                "source_sha": "abc123",
            }
        )
