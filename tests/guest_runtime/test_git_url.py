from __future__ import annotations

import pytest

from core.guest_runtime.git_url import (
    commit_sha_from_git_url,
    normalize_code_agent_git_remote,
    parse_ls_remote_head,
    resolve_code_agent_source_sha,
)


def test_normalize_github_tree_url() -> None:
    assert (
        normalize_code_agent_git_remote("https://github.com/zub123123123/cheetah-agent/tree/main")
        == "https://github.com/zub123123123/cheetah-agent.git"
    )


def test_normalize_github_blob_and_commit_urls() -> None:
    assert (
        normalize_code_agent_git_remote(
            "https://github.com/zub123123123/cheetah-agent/blob/main/main.py"
        )
        == "https://github.com/zub123123123/cheetah-agent.git"
    )
    assert (
        normalize_code_agent_git_remote(
            "https://www.github.com/zub123123123/cheetah-agent/commit/"
            "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
        )
        == "https://github.com/zub123123123/cheetah-agent.git"
    )


def test_normalize_github_dot_git_and_file_url() -> None:
    assert (
        normalize_code_agent_git_remote("https://github.com/zub123123123/cheetah-agent.git")
        == "https://github.com/zub123123123/cheetah-agent.git"
    )
    local = "file:///tmp/cheetah.git"
    assert normalize_code_agent_git_remote(local) == local


def test_normalize_keeps_org_named_like_web_marker() -> None:
    assert (
        normalize_code_agent_git_remote("https://github.com/src/cheetah-agent/tree/main")
        == "https://github.com/src/cheetah-agent.git"
    )


def test_normalize_gitlab_gitea_and_ssh() -> None:
    assert (
        normalize_code_agent_git_remote(
            "https://gitlab.example.com/group/sub/project/-/tree/main"
        )
        == "https://gitlab.example.com/group/sub/project.git"
    )
    assert (
        normalize_code_agent_git_remote(
            "http://git.internal:3000/org/repo/src/branch/main"
        )
        == "http://git.internal:3000/org/repo.git"
    )
    ssh = "ssh://git@gitlab.example.com/group/project.git"
    assert normalize_code_agent_git_remote(ssh) == ssh
    scp = "git@gitlab.example.com:group/project.git"
    assert normalize_code_agent_git_remote(scp) == scp


def test_normalize_git_url_rejects_empty_and_incomplete() -> None:
    with pytest.raises(ValueError, match="git_url required"):
        normalize_code_agent_git_remote("   ")
    with pytest.raises(ValueError, match="owner/repo"):
        normalize_code_agent_git_remote("https://github.com/only-owner")
    with pytest.raises(ValueError, match="owner/repo"):
        normalize_code_agent_git_remote("https://gitlab.example.com/only-group")


def test_commit_sha_from_commit_url() -> None:
    sha = commit_sha_from_git_url(
        "https://github.com/zub123123123/cheetah-agent/commit/"
        "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
    )
    assert sha == "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
    assert (
        commit_sha_from_git_url(
            "https://gitlab.example.com/group/project/-/commit/"
            "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
        )
        == "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
    )


def test_commit_sha_rejects_tree_and_short() -> None:
    with pytest.raises(ValueError, match="not a commit URL"):
        commit_sha_from_git_url("https://github.com/zub123123123/cheetah-agent/tree/main")
    with pytest.raises(ValueError, match="40 hex"):
        commit_sha_from_git_url(
            "https://github.com/zub123123123/cheetah-agent/commit/abc123"
        )


def test_resolve_source_sha_prefers_explicit() -> None:
    assert (
        resolve_code_agent_source_sha(
            git_url="https://gitlab.example.com/group/project/-/tree/main",
            source_sha="70eb6c3c6909d1f975d9c7e6c723bae5db897478",
        )
        == "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
    )
    assert (
        resolve_code_agent_source_sha(
            git_url=(
                "https://www.github.com/zub123123123/cheetah-agent/commit/"
                "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
            ),
            source_sha="  ",
        )
        == "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
    )


def test_resolve_source_sha_clone_url_defers_head() -> None:
    assert (
        resolve_code_agent_source_sha(
            git_url="https://github.com/zub123123123/cheetah-agent.git",
            source_sha="",
        )
        == ""
    )


def test_parse_ls_remote_head() -> None:
    assert (
        parse_ls_remote_head(
            "70eb6c3c6909d1f975d9c7e6c723bae5db897478\tHEAD\n"
            "70eb6c3c6909d1f975d9c7e6c723bae5db897478\trefs/heads/main\n",
            remote_url="https://github.com/zub123123123/cheetah-agent.git",
        )
        == "70eb6c3c6909d1f975d9c7e6c723bae5db897478"
    )
    with pytest.raises(ValueError, match="no refs"):
        parse_ls_remote_head("  \n", remote_url="https://example.test/repo.git")
    with pytest.raises(ValueError, match="malformed"):
        parse_ls_remote_head(
            "70eb6c3c6909d1f975d9c7e6c723bae5db897478 refs/heads/main\n",
            remote_url="https://example.test/repo.git",
        )
