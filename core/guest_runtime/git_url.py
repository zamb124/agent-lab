"""Нормализация git remote для ingest исходников code_agent."""

from __future__ import annotations

import re
from urllib.parse import ParseResult, urlparse

_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_COMMIT_PATH_MARKERS = frozenset({"commit", "commits"})
# HTML-хвост страницы хостинга, не путь git remote.
_WEB_PATH_MARKERS = frozenset(
    {
        "-",
        "tree",
        "blob",
        "commit",
        "commits",
        "raw",
        "src",
        "pull",
        "releases",
        "issues",
        "branch",
    }
)


def normalize_code_agent_git_remote(git_url: str) -> str:
    """HTTP(S) страница репозитория → ``{scheme}://{host}/{path}.git``.

    Хост и схема из URL, не github.com. ``/tree/``, ``/blob/``, ``/commit/``,
    GitLab ``/-/…`` срезаются. ``file://``, ``ssh://``, ``git@host:path`` и
    локальный путь без ``://`` — как есть. Имя ветки (`main`) не подставляем.
    """
    stripped = git_url.strip()
    if stripped == "":
        raise ValueError("git_url required")
    if "://" not in stripped:
        return stripped
    parsed = urlparse(stripped)
    if parsed.scheme == "file":
        return stripped
    if parsed.scheme not in {"http", "https"}:
        return stripped
    hostname = parsed.hostname
    if hostname is None or hostname.strip() == "":
        raise ValueError(f"git_url has no hostname: {git_url}")
    repo_path = _http_repo_path(parsed.path, git_url=git_url)
    return f"{parsed.scheme}://{_http_netloc(parsed)}/{repo_path}.git"


def is_code_agent_commit_sha(value: str) -> bool:
    return _COMMIT_SHA_RE.fullmatch(value) is not None


def git_url_has_commit_path(git_url: str) -> bool:
    stripped = git_url.strip()
    if stripped == "":
        return False
    parsed = urlparse(stripped)
    parts = [segment for segment in parsed.path.strip("/").split("/") if segment]
    return any(segment in _COMMIT_PATH_MARKERS for segment in parts)


def commit_sha_from_git_url(git_url: str) -> str:
    """SHA из URL с сегментом ``commit``/``commits`` и 40 hex."""
    stripped = git_url.strip()
    if stripped == "":
        raise ValueError("git_url required")
    parsed = urlparse(stripped)
    parts = [segment for segment in parsed.path.strip("/").split("/") if segment]
    for index, segment in enumerate(parts):
        if segment not in _COMMIT_PATH_MARKERS:
            continue
        if index + 1 >= len(parts):
            raise ValueError(f"git_url commit SHA must be 40 hex chars: {git_url}")
        sha = parts[index + 1]
        if _COMMIT_SHA_RE.match(sha) is None:
            raise ValueError(f"git_url commit SHA must be 40 hex chars: {git_url}")
        return sha.lower()
    raise ValueError(f"git_url is not a commit URL: {git_url}")


def resolve_code_agent_source_sha(*, git_url: str, source_sha: str) -> str:
    """Явный SHA или SHA из commit-URL. Пустая строка — ingest делает ``ls-remote HEAD``."""
    stripped = source_sha.strip()
    if stripped:
        return stripped
    if git_url_has_commit_path(git_url):
        return commit_sha_from_git_url(git_url)
    return ""


def parse_ls_remote_head(output: str, *, remote_url: str) -> str:
    """Первая строка ``git ls-remote <remote> HEAD`` → 40 hex."""
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) == 0:
        raise ValueError(f"git ls-remote HEAD returned no refs: {remote_url}")
    head_line = ""
    for line in lines:
        _sha, tab, ref = line.partition("\t")
        if tab != "" and ref.strip() == "HEAD":
            head_line = line
            break
    if head_line == "":
        raise ValueError(f"git ls-remote HEAD malformed: {remote_url}: {lines[0]!r}")
    sha, _tab, _ref = head_line.partition("\t")
    if _COMMIT_SHA_RE.match(sha) is None:
        raise ValueError(f"git ls-remote HEAD SHA must be 40 hex: {remote_url}")
    return sha.lower()


def _http_netloc(parsed: ParseResult) -> str:
    hostname = parsed.hostname
    netloc = parsed.netloc
    if hostname is not None and hostname.startswith("www."):
        return netloc.replace(hostname, hostname[4:], 1)
    return netloc


def _http_repo_path(path: str, *, git_url: str) -> str:
    segments = [segment for segment in path.strip("/").split("/") if segment]
    had_git_suffix = False
    if segments and segments[-1].endswith(".git"):
        had_git_suffix = True
        stem = segments[-1][: -len(".git")]
        if stem == "":
            segments = segments[:-1]
        else:
            segments[-1] = stem
    min_repo = 1 if had_git_suffix else 2
    cut = len(segments)
    for index, segment in enumerate(segments):
        if index < min_repo:
            continue
        if segment in _WEB_PATH_MARKERS:
            cut = index
            break
    repo_segments = segments[:cut]
    if len(repo_segments) == 0:
        raise ValueError(f"git_url must contain a repository path: {git_url}")
    if len(repo_segments) < 2 and not had_git_suffix:
        raise ValueError(f"git_url must contain owner/repo: {git_url}")
    return "/".join(repo_segments)
