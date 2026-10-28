"""Load UI Kit catalog and component manifests for playground and doc generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.types import JsonObject, JsonValue, parse_yaml_value, require_json_object

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DS_ROOT = _REPO_ROOT / "tests" / "ui" / "design-system"
_CATALOG_PATH = _DS_ROOT / "catalog.yaml"
# Манифест ссылается на модуль по алиасу сборки; страница preview грузит собранный модуль из embed-dist по URL.
_IMPORT_SPECIFIER_PREFIX = "@platform/lib/"
_IMPORT_URL_PREFIX = "/static/core/lib/"


@dataclass(frozen=True)
class UiKitVariant:
    id: str
    props: JsonObject


@dataclass(frozen=True)
class UiKitManifest:
    component: str
    doc_slug: str
    tier: str
    title_ru: str
    title_en: str
    import_url: str
    variants: tuple[UiKitVariant, ...]


@dataclass(frozen=True)
class UiKitCatalogEntry:
    component: str
    doc_slug: str
    status: str
    tier: str
    deadline: str | None = None


def _require_mapping(raw: JsonValue, label: str) -> JsonObject:
    return require_json_object(raw, label)


def _load_yaml_object(text: str, label: str) -> JsonObject:
    loaded = parse_yaml_value(text, label)
    if loaded is None:
        empty: JsonObject = {}
        return empty
    return _require_mapping(loaded, label)


def load_catalog() -> tuple[UiKitCatalogEntry, ...]:
    if not _CATALOG_PATH.is_file():
        raise FileNotFoundError(f"UI Kit catalog not found: {_CATALOG_PATH}")
    catalog = _load_yaml_object(_CATALOG_PATH.read_text(encoding="utf-8"), "catalog.yaml")
    entries_raw = catalog.get("components")
    if not isinstance(entries_raw, list):
        raise ValueError("catalog.yaml components must be a list")
    entries: list[UiKitCatalogEntry] = []
    for item in entries_raw:
        entry = _require_mapping(item, "catalog entry")
        component = entry.get("component")
        doc_slug = entry.get("doc_slug")
        status = entry.get("status")
        tier = entry.get("tier")
        if not isinstance(component, str) or not component.startswith("platform-"):
            raise ValueError(f"invalid catalog component: {component!r}")
        if not isinstance(doc_slug, str) or not doc_slug:
            raise ValueError(f"invalid doc_slug for {component}")
        if not isinstance(status, str) or not status:
            raise ValueError(f"invalid status for {component}")
        if not isinstance(tier, str) or not tier:
            raise ValueError(f"invalid tier for {component}")
        deadline_raw = entry.get("deadline")
        deadline = deadline_raw if isinstance(deadline_raw, str) else None
        entries.append(
            UiKitCatalogEntry(
                component=component,
                doc_slug=doc_slug,
                status=status,
                tier=tier,
                deadline=deadline,
            )
        )
    return tuple(entries)


def load_manifest(component: str) -> UiKitManifest:
    manifest_path = _DS_ROOT / "components" / component / "manifest.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found for {component}: {manifest_path}")
    manifest = _load_yaml_object(
        manifest_path.read_text(encoding="utf-8"),
        f"{component} manifest.yaml",
    )
    import_specifier = manifest.get("import")
    if not isinstance(import_specifier, str) or not import_specifier.startswith(_IMPORT_SPECIFIER_PREFIX):
        raise ValueError(f"{component}: manifest import must start with {_IMPORT_SPECIFIER_PREFIX}")
    variants_raw = manifest.get("variants")
    if not isinstance(variants_raw, list) or not variants_raw:
        raise ValueError(f"{component}: manifest variants must be a non-empty list")
    variants: list[UiKitVariant] = []
    for variant_item in variants_raw:
        variant = _require_mapping(variant_item, f"{component} variant")
        variant_id = variant.get("id")
        props_raw = variant.get("props")
        if not isinstance(variant_id, str) or not variant_id:
            raise ValueError(f"{component}: variant id is required")
        props = require_json_object(props_raw, f"{component} variant props")
        variants.append(UiKitVariant(id=variant_id, props=props))
    for key in ("doc_slug", "tier", "title_ru", "title_en"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{component}: manifest {key} is required")
    manifest_component = manifest.get("component")
    if manifest_component != component:
        raise ValueError(f"{component}: manifest component mismatch ({manifest_component!r})")
    return UiKitManifest(
        component=component,
        doc_slug=str(manifest["doc_slug"]),
        tier=str(manifest["tier"]),
        title_ru=str(manifest["title_ru"]),
        title_en=str(manifest["title_en"]),
        import_url=f"{_IMPORT_URL_PREFIX}{import_specifier.removeprefix(_IMPORT_SPECIFIER_PREFIX)}",
        variants=tuple(variants),
    )


def resolve_variant(component: str, variant_id: str) -> UiKitVariant:
    manifest = load_manifest(component)
    for variant in manifest.variants:
        if variant.id == variant_id:
            return variant
    available = ", ".join(v.id for v in manifest.variants)
    raise ValueError(f"unknown variant {variant_id!r} for {component}; available: {available}")


def catalog_allows_component(component: str) -> bool:
    for entry in load_catalog():
        if entry.component == component:
            return True
    return False
