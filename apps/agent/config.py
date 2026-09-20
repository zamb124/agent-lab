"""
Конфигурация LinnexAgent (releases, tunnel).
"""

import os

from core.config.loader import load_merged_config
from core.config.models import AgentReleaseSettings, AgentSettings
from core.types import JsonObject

__all__ = [
    "AgentReleaseSettings",
    "AgentSettings",
    "get_agent_settings",
    "reset_agent_settings",
]


_agent_settings: AgentSettings | None = None


def get_agent_settings() -> AgentSettings:
    global _agent_settings
    if _agent_settings is None:
        merged_config = load_merged_config(service_name="frontend", silent=True)
        agent_section_raw = merged_config.get("agent")
        if agent_section_raw is None:
            agent_section: JsonObject = {}
        elif isinstance(agent_section_raw, dict):
            agent_section = dict(agent_section_raw)
        else:
            raise TypeError("agent config section must be a mapping")
        env_github_base = os.environ.get("AGENT__RELEASES__GITHUB_API_BASE_URL")
        env_github_owner = os.environ.get("AGENT__RELEASES__GITHUB_OWNER")
        env_github_repo = os.environ.get("AGENT__RELEASES__GITHUB_REPO")
        env_github_token = os.environ.get("AGENT__RELEASES__GITHUB_TOKEN")
        env_release_source = os.environ.get("AGENT__RELEASES__SOURCE")
        if (
            env_github_base is not None
            or env_github_owner is not None
            or env_github_repo is not None
            or env_github_token is not None
            or env_release_source is not None
        ):
            releases_raw = agent_section.get("releases")
            if isinstance(releases_raw, dict):
                releases_section = dict(releases_raw)
            else:
                releases_section = {}
            if env_github_base is not None:
                releases_section["github_api_base_url"] = env_github_base
            if env_github_owner is not None:
                releases_section["github_owner"] = env_github_owner
            if env_github_repo is not None:
                releases_section["github_repo"] = env_github_repo
            if env_github_token is not None:
                releases_section["github_token"] = env_github_token
            if env_release_source is not None:
                releases_section["source"] = env_release_source
            agent_section["releases"] = releases_section
        if not agent_section:
            _agent_settings = AgentSettings()
        else:
            _agent_settings = AgentSettings.model_validate(agent_section)
    return _agent_settings


def reset_agent_settings() -> None:
    global _agent_settings
    _agent_settings = None
