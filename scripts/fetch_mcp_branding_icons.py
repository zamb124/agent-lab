"""Maintainer: обновить brand SVG/PNG в git-бандле из MCP registry + Simple Icons."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MANIFEST = _REPO_ROOT / "apps/flows/mcp_branding/manifest.yaml"
_SIMPLE_ICONS_CDN = "https://cdn.jsdelivr.net/npm/simple-icons/icons/{slug}.svg"
_SIMPLE_ICONS_INDEX = "https://cdn.jsdelivr.net/npm/simple-icons/data/simple-icons.json"
_REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0/servers"
_SOURCES_MD = _REPO_ROOT / "apps/flows/mcp_branding/SOURCES.md"

_GENERIC_SEGMENTS = frozenset({
    "mcp",
    "server",
    "api",
    "tools",
    "tool",
    "catalog",
    "docs",
    "doc",
    "mcp-server",
})
_NAMESPACE_SEGMENTS = frozenset({
    "com",
    "io",
    "ai",
    "app",
    "dev",
    "org",
    "net",
    "co",
    "tools",
})

# Явные overrides, когда эвристика не попадает в slug Simple Icons.
_REGISTRY_SIMPLE_ICON: dict[str, str] = {
    "com.notion/mcp": "notion",
    "com.stripe/mcp": "stripe",
    "com.supabase/mcp": "supabase",
    "app.linear/linear": "linear",
    "io.brandfetch/brandfetch": "brandfetch",
    "io.github.modelcontextprotocol/filesystem": "github",
    "com.github/github": "github",
    "com.brave/search": "brave",
    "com.sentry/sentry": "sentry",
    "com.docker/mcp": "docker",
    "com.slack/slack": "slack",
    "ai.waystation/postgres": "postgresql",
    "com.microsoft/playwright-mcp": "microsoft",
    "com.context7/mcp": "context7",
    "com.deepwiki/mcp": "deepwiki",
}

_PLATFORM_ENTRIES = (
    {"server_id": "browser", "file": "icons/browser.svg", "source": "platform", "license": "internal"},
    {"server_id": "search", "file": "icons/search.svg", "source": "platform", "license": "internal"},
    {"server_id": "deepwiki", "file": "icons/deepwiki.svg", "source": "custom", "license": "internal"},
    {"server_id": "context7_catalog", "file": "icons/context7_catalog.svg", "source": "custom", "license": "internal"},
)


@dataclass(frozen=True)
class RegistryServerRow:
    registry_name: str
    server_id: str
    title: str | None
    icon_url: str | None
    icon_mime: str | None


@dataclass(frozen=True)
class FetchResult:
    server_id: str
    registry_name: str
    rel_file: str
    source: str
    license_name: str


def _catalog_id_from_registry_name(registry_name: str) -> str:
    raw = registry_name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if not slug:
        raise ValueError("registry_name is empty after slugify")
    if not slug[0].isalpha():
        slug = f"mcp_{slug}"
    if len(slug) > 64:
        slug = slug[:64].rstrip("_")
    return slug


def _is_low_quality_icon_source(source: str) -> bool:
    if not source.startswith("simple-icons/"):
        return False
    slug = source.removeprefix("simple-icons/")
    return len(slug) < 3


def _fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "humanitec-mcp-branding-fetch/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def _load_simple_icon_slugs() -> frozenset[str]:
    payload = json.loads(_fetch_bytes(_SIMPLE_ICONS_INDEX))
    if not isinstance(payload, list):
        raise ValueError("simple-icons index must be a list")
    slugs: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        slug_raw = row.get("slug")
        if isinstance(slug_raw, str) and slug_raw.strip():
            slugs.add(slug_raw.strip())
    return frozenset(slugs)


def _fetch_simple_icon(slug: str) -> bytes:
    url = _SIMPLE_ICONS_CDN.format(slug=urllib.parse.quote(slug))
    return _fetch_bytes(url)


def _extension_for_mime(mime_type: str | None) -> str:
    if mime_type == "image/png":
        return ".png"
    if mime_type == "image/webp":
        return ".webp"
    if mime_type in ("image/jpeg", "image/jpg"):
        return ".jpg"
    return ".svg"


def _simple_icon_slug_candidates(
    *,
    registry_name: str,
    title: str | None,
    simple_icon_slugs: frozenset[str],
) -> list[str]:
    override = _REGISTRY_SIMPLE_ICON.get(registry_name)
    if override is not None:
        return [override]

    candidates: list[str] = []
    parts = re.split(r"[/._-]+", registry_name.lower())
    for part in reversed(parts):
        if not part or part in _NAMESPACE_SEGMENTS or part in _GENERIC_SEGMENTS:
            continue
        if len(part) <= 2:
            continue
        candidates.append(part)

    if title is not None and title.strip():
        title_compact = re.sub(r"[^a-z0-9]+", "", title.lower())
        if len(title_compact) > 2:
            candidates.append(title_compact)
        title_words = re.findall(r"[a-z0-9]+", title.lower())
        for word in title_words:
            if word not in _GENERIC_SEGMENTS and word not in _NAMESPACE_SEGMENTS and len(word) > 2:
                candidates.append(word)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)

    expanded: list[str] = []
    for candidate in deduped:
        expanded.append(candidate)
        if candidate in simple_icon_slugs:
            continue
        for slug in sorted(simple_icon_slugs):
            if len(slug) < 4:
                continue
            if slug == candidate:
                expanded.append(slug)
                break
            if len(candidate) >= 4 and (slug.startswith(candidate) or candidate.startswith(slug)):
                expanded.append(slug)
                break

    final: list[str] = []
    seen_final: set[str] = set()
    for candidate in expanded:
        if candidate in seen_final:
            continue
        seen_final.add(candidate)
        final.append(candidate)
    return final


def _iter_registry_servers(*, max_pages: int) -> list[RegistryServerRow]:
    cursor: str | None = None
    rows: list[RegistryServerRow] = []
    seen_names: set[str] = set()

    for _ in range(max_pages):
        list_url = f"{_REGISTRY_BASE}?limit=100"
        if cursor is not None:
            list_url = f"{list_url}&cursor={urllib.parse.quote(cursor)}"
        payload = json.loads(_fetch_bytes(list_url))
        if not isinstance(payload, dict):
            raise ValueError("registry list response must be an object")

        servers_raw = payload.get("servers")
        if not isinstance(servers_raw, list):
            raise ValueError("registry list servers must be an array")

        for item in servers_raw:
            if not isinstance(item, dict):
                continue
            meta = item.get("_meta")
            if not isinstance(meta, dict):
                continue
            official = meta.get("io.modelcontextprotocol.registry/official")
            if not isinstance(official, dict):
                continue
            if official.get("isLatest") is not True:
                continue

            server = item.get("server")
            if not isinstance(server, dict):
                continue
            registry_name_raw = server.get("name")
            if not isinstance(registry_name_raw, str) or not registry_name_raw.strip():
                continue
            registry_name = registry_name_raw.strip()
            if registry_name in seen_names:
                continue
            seen_names.add(registry_name)

            title_raw = server.get("title")
            title = title_raw.strip() if isinstance(title_raw, str) and title_raw.strip() else None

            icon_url: str | None = None
            icon_mime: str | None = None
            icons = server.get("icons")
            if isinstance(icons, list) and icons:
                first = icons[0]
                if isinstance(first, dict):
                    src_raw = first.get("src")
                    if isinstance(src_raw, str) and src_raw.strip():
                        icon_url = src_raw.strip()
                    mime_raw = first.get("mimeType")
                    if isinstance(mime_raw, str) and mime_raw.strip():
                        icon_mime = mime_raw.strip()

            server_id = _catalog_id_from_registry_name(registry_name)
            rows.append(
                RegistryServerRow(
                    registry_name=registry_name,
                    server_id=server_id,
                    title=title,
                    icon_url=icon_url,
                    icon_mime=icon_mime,
                )
            )

        metadata = payload.get("metadata")
        next_cursor: str | None = None
        if isinstance(metadata, dict):
            cursor_raw = metadata.get("nextCursor")
            if isinstance(cursor_raw, str) and cursor_raw.strip():
                next_cursor = cursor_raw.strip()
        cursor = next_cursor
        if cursor is None:
            break

    return rows


def _resolve_icon_bytes(
    row: RegistryServerRow,
    *,
    simple_icon_slugs: frozenset[str],
) -> tuple[bytes, str, str, str] | None:
    if row.icon_url is not None:
        try:
            payload = _fetch_bytes(row.icon_url)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(f"warn publisher icon failed for {row.registry_name}: {exc}", flush=True)
        else:
            ext = _extension_for_mime(row.icon_mime)
            return payload, ext, row.icon_url, "publisher"

    for slug in _simple_icon_slug_candidates(
        registry_name=row.registry_name,
        title=row.title,
        simple_icon_slugs=simple_icon_slugs,
    ):
        if slug not in simple_icon_slugs:
            continue
        if len(slug) < 3:
            continue
        try:
            payload = _fetch_simple_icon(slug)
        except urllib.error.HTTPError:
            continue
        return payload, ".svg", f"simple-icons/{slug}", "MIT"

    return None


def _load_manifest(path: Path) -> tuple[Path, dict[str, object], list[dict[str, object]]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("manifest root must be a mapping")
    entries_raw = parsed.get("entries")
    if entries_raw is None:
        entries_raw = []
    if not isinstance(entries_raw, list):
        raise ValueError("manifest entries must be a list")
    typed_entries: list[dict[str, object]] = []
    for row in entries_raw:
        if not isinstance(row, dict):
            raise ValueError(f"invalid manifest entry: {row!r}")
        typed_entries.append(row)
    return path.parent, parsed, typed_entries


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_sources_md(entries: list[dict[str, object]]) -> None:
    lines = [
        "# MCP branding icon sources",
        "",
        "| server_id | file | source | license |",
        "|---|---|---|---|",
        "| _generic | icons/_generic.svg | platform custom | internal |",
    ]
    for row in sorted(entries, key=lambda item: str(item.get("server_id", ""))):
        server_id = row.get("server_id")
        file_name = row.get("file")
        source = row.get("source")
        license_name = row.get("license")
        if not isinstance(server_id, str):
            continue
        if not isinstance(file_name, str):
            continue
        if not isinstance(source, str):
            continue
        if not isinstance(license_name, str):
            continue
        lines.append(f"| {server_id} | {file_name} | {source} | {license_name} |")
    lines.extend(
        [
            "",
            "Simple Icons: https://github.com/simple-icons/simple-icons (MIT)",
            "",
        ]
    )
    _ = _SOURCES_MD.write_text("\n".join(lines), encoding="utf-8")


def _sync_manifest_from_icon_files(
    *,
    manifest_path: Path,
    entries_raw: list[dict[str, object]],
    entries_by_id: dict[str, dict[str, object]],
    bundle_dir: Path,
    icons_dir: Path,
) -> int:
    """Добавляет manifest entries для icon-файлов на диске без записи (после прерванного fetch)."""
    synced = 0
    for icon_path in sorted(icons_dir.iterdir()):
        if not icon_path.is_file():
            continue
        if icon_path.name.startswith("_"):
            continue
        server_id = icon_path.stem
        if server_id in entries_by_id:
            continue
        rel_file = f"icons/{icon_path.name}"
        new_entry: dict[str, object] = {
            "server_id": server_id,
            "file": rel_file,
            "source": "recovered-local",
            "license": "unknown",
        }
        entries_raw.append(new_entry)
        entries_by_id[server_id] = new_entry
        synced += 1
    return synced


def fetch_icons_from_registry(
    *,
    manifest_path: Path,
    dry_run: bool,
    max_pages: int,
    refresh_existing: bool,
) -> None:
    bundle_dir, manifest, entries_raw = _load_manifest(manifest_path)
    icons_dir = bundle_dir / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    entries_by_id: dict[str, dict[str, object]] = {}
    for row in entries_raw:
        server_id_raw = row.get("server_id")
        if not isinstance(server_id_raw, str) or not server_id_raw.strip():
            raise ValueError(f"entry server_id required: {row!r}")
        entries_by_id[server_id_raw.strip()] = row

    for platform_entry in _PLATFORM_ENTRIES:
        server_id_raw = platform_entry["server_id"]
        if not isinstance(server_id_raw, str):
            continue
        if server_id_raw not in entries_by_id:
            entries_raw.append(dict(platform_entry))
            entries_by_id[server_id_raw] = platform_entry

    synced_orphans = _sync_manifest_from_icon_files(
        manifest_path=manifest_path,
        entries_raw=entries_raw,
        entries_by_id=entries_by_id,
        bundle_dir=bundle_dir,
        icons_dir=icons_dir,
    )
    if synced_orphans > 0 and not dry_run:
        manifest["entries"] = sorted(
            entries_raw,
            key=lambda item: str(item.get("server_id", "")) if isinstance(item, dict) else "",
        )
        _write_manifest(manifest_path, manifest)
        typed_sorted = [row for row in manifest["entries"] if isinstance(row, dict)]
        _write_sources_md(typed_sorted)
        print(f"synced orphan icon files into manifest: {synced_orphans}", flush=True)
    elif synced_orphans > 0:
        print(f"synced orphan icon files into manifest (dry-run): {synced_orphans}", flush=True)

    simple_icon_slugs = _load_simple_icon_slugs()
    registry_rows = _iter_registry_servers(max_pages=max_pages)

    matched = 0
    skipped_existing = 0
    skipped_no_source = 0

    for index, row in enumerate(registry_rows, start=1):
        if index % 200 == 0:
            print(
                f"progress {index}/{len(registry_rows)} matched={matched} skipped_existing={skipped_existing}",
                flush=True,
            )

        existing = entries_by_id.get(row.server_id)
        low_quality = False
        if existing is not None and not refresh_existing:
            file_raw = existing.get("file")
            source_raw = existing.get("source")
            low_quality = isinstance(source_raw, str) and _is_low_quality_icon_source(source_raw)
            if (
                isinstance(file_raw, str)
                and (bundle_dir / file_raw).is_file()
                and not low_quality
            ):
                skipped_existing += 1
                continue
            if low_quality and isinstance(file_raw, str):
                stale_path = bundle_dir / file_raw
                if stale_path.is_file() and not dry_run:
                    stale_path.unlink()

        resolved = _resolve_icon_bytes(row, simple_icon_slugs=simple_icon_slugs)
        if resolved is None:
            if low_quality and existing is not None and not dry_run:
                entries_raw.remove(existing)
                del entries_by_id[row.server_id]
            skipped_no_source += 1
            print(f"skip {row.registry_name} ({row.server_id}): no icon source")
            continue

        payload, ext, source, license_name = resolved
        rel_file = f"icons/{row.server_id}{ext}"
        icon_path = icons_dir / f"{row.server_id}{ext}"

        if not dry_run:
            icon_path.write_bytes(payload)
            entry = entries_by_id.get(row.server_id)
            if entry is None:
                new_entry: dict[str, object] = {
                    "server_id": row.server_id,
                    "file": rel_file,
                    "source": source,
                    "license": license_name,
                }
                entries_raw.append(new_entry)
                entries_by_id[row.server_id] = new_entry
            else:
                entry["file"] = rel_file
                entry["source"] = source
                entry["license"] = license_name

        matched += 1
        print(f"{'dry-run' if dry_run else 'updated'} {row.server_id} <- {source}", flush=True)

        if not dry_run and matched % 50 == 0:
            manifest["entries"] = sorted(
                entries_raw,
                key=lambda item: str(item.get("server_id", "")) if isinstance(item, dict) else "",
            )
            _write_manifest(manifest_path, manifest)

    if not dry_run:
        manifest["entries"] = sorted(
            entries_raw,
            key=lambda item: str(item.get("server_id", "")) if isinstance(item, dict) else "",
        )
        _write_manifest(manifest_path, manifest)
        typed_sorted = [row for row in manifest["entries"] if isinstance(row, dict)]
        _write_sources_md(typed_sorted)

    print(
        "registry fetch done:",
        f"registry_rows={len(registry_rows)}",
        f"matched={matched}",
        f"skipped_existing={skipped_existing}",
        f"skipped_no_source={skipped_no_source}",
        f"dry_run={dry_run}",
    )


def fetch_icons(
    *,
    manifest_path: Path,
    registry_names: list[str],
    dry_run: bool,
) -> None:
    bundle_dir, manifest, entries_raw = _load_manifest(manifest_path)
    icons_dir = bundle_dir / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    entries_by_id: dict[str, dict[str, object]] = {}
    for row in entries_raw:
        server_id_raw = row.get("server_id")
        if not isinstance(server_id_raw, str) or not server_id_raw.strip():
            raise ValueError(f"entry server_id required: {row!r}")
        entries_by_id[server_id_raw.strip()] = row

    simple_icon_slugs = _load_simple_icon_slugs()
    updated = 0
    for registry_name in registry_names:
        server_id = _catalog_id_from_registry_name(registry_name)
        row = RegistryServerRow(
            registry_name=registry_name,
            server_id=server_id,
            title=None,
            icon_url=None,
            icon_mime=None,
        )
        resolved = _resolve_icon_bytes(row, simple_icon_slugs=simple_icon_slugs)
        if resolved is None:
            print(f"skip {registry_name} ({server_id}): no icon source")
            continue

        payload, ext, source, license_name = resolved
        rel_file = f"icons/{server_id}{ext}"
        icon_path = icons_dir / f"{server_id}{ext}"

        if not dry_run:
            icon_path.write_bytes(payload)
            entry = entries_by_id.get(server_id)
            if entry is None:
                new_entry: dict[str, object] = {
                    "server_id": server_id,
                    "file": rel_file,
                    "source": source,
                    "license": license_name,
                }
                entries_raw.append(new_entry)
                entries_by_id[server_id] = new_entry
            else:
                entry["file"] = rel_file
                entry["source"] = source
                entry["license"] = license_name

        print(f"{'dry-run' if dry_run else 'updated'} {server_id} <- {source}")
        updated += 1

    if not dry_run and updated > 0:
        manifest["entries"] = entries_raw
        _write_manifest(manifest_path, manifest)

    print(f"fetch done: updated={updated} dry_run={dry_run}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch MCP branding icons into git bundle")
    _ = parser.add_argument(
        "--manifest-path",
        type=Path,
        default=_DEFAULT_MANIFEST,
        help="Path to manifest.yaml",
    )
    _ = parser.add_argument(
        "--from-registry",
        action="store_true",
        help="Scan official MCP registry and auto-match icons (max coverage)",
    )
    _ = parser.add_argument(
        "--max-pages",
        type=int,
        default=300,
        help="Registry pagination limit when --from-registry (100 servers per page)",
    )
    _ = parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Re-fetch icons even if manifest entry already has a local file",
    )
    _ = parser.add_argument(
        "--registry-name",
        action="append",
        dest="registry_names",
        help="Registry name to fetch (repeatable). Used without --from-registry.",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write files",
    )
    _ = parser.add_argument(
        "--sync-manifest-only",
        action="store_true",
        help="Only sync manifest entries from existing icon files, then exit",
    )
    args = parser.parse_args()

    if args.sync_manifest_only:
        bundle_dir, manifest, entries_raw = _load_manifest(args.manifest_path)
        icons_dir = bundle_dir / "icons"
        entries_by_id: dict[str, dict[str, object]] = {}
        for row in entries_raw:
            server_id_raw = row.get("server_id")
            if not isinstance(server_id_raw, str) or not server_id_raw.strip():
                raise ValueError(f"entry server_id required: {row!r}")
            entries_by_id[server_id_raw.strip()] = row
        synced = _sync_manifest_from_icon_files(
            manifest_path=args.manifest_path,
            entries_raw=entries_raw,
            entries_by_id=entries_by_id,
            bundle_dir=bundle_dir,
            icons_dir=icons_dir,
        )
        if synced > 0 and not args.dry_run:
            manifest["entries"] = sorted(
                entries_raw,
                key=lambda item: str(item.get("server_id", "")) if isinstance(item, dict) else "",
            )
            _write_manifest(args.manifest_path, manifest)
            typed_sorted = [row for row in manifest["entries"] if isinstance(row, dict)]
            _write_sources_md(typed_sorted)
        print(f"sync-manifest-only: synced={synced} dry_run={args.dry_run}")
        return

    if args.from_registry:
        fetch_icons_from_registry(
            manifest_path=args.manifest_path,
            dry_run=args.dry_run,
            max_pages=args.max_pages,
            refresh_existing=args.refresh_existing,
        )
        return

    registry_names = args.registry_names
    if not registry_names:
        registry_names = list(_REGISTRY_SIMPLE_ICON.keys())

    fetch_icons(
        manifest_path=args.manifest_path,
        registry_names=registry_names,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
