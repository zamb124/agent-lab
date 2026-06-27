"""
Конфигурация HumanitecAgent (releases, tunnel).
"""

import os

from pydantic import BaseModel, Field

from core.config.loader import load_merged_config
from core.types import JsonObject


class AgentReleaseSettings(BaseModel):
    """Источник артефактов HumanitecAgent для download redirect."""

    github_owner: str = Field(default="zamb124", description="GitHub org/user releases")
    github_repo: str = Field(default="agent-lab", description="GitHub repo с арtefактами")
    github_api_base_url: str | None = Field(
        default=None,
        description="Override GitHub API base; default https://api.github.com",
    )
    source: str = Field(
        default="github",
        description="github — GitHub Releases API; local — dist/ артефакт",
    )


class AgentSettings(BaseModel):
    """Настройки HumanitecAgent на frontend сервисе."""

    releases: AgentReleaseSettings = Field(default_factory=AgentReleaseSettings)
    pairing_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    tunnel_online_ttl_seconds: int = Field(default=120, ge=30, le=3600)
    pairing_rate_limit_per_hour: int = Field(default=20, ge=1, le=200)
    register_rate_limit_per_hour: int = Field(default=60, ge=1, le=500)


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
        env_release_source = os.environ.get("AGENT__RELEASES__SOURCE")
        if (
            env_github_base is not None
            or env_github_owner is not None
            or env_github_repo is not None
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
