"""Загрузка docs/scenarios/taxonomy.yaml для docs_prepare и quality gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_SCENARIO_TAG = "general"


@dataclass(frozen=True)
class TagSpec:
    label_ru: str
    label_en: str
    order: int


@dataclass(frozen=True)
class ServiceSpec:
    key: str
    label_ru: str
    label_en: str
    intro_ru: str
    intro_en: str
    featured_slug: str | None
    tags: dict[str, TagSpec]


@dataclass(frozen=True)
class LearningPathStep:
    label_ru: str
    label_en: str
    href: str


@dataclass(frozen=True)
class LearningPath:
    path_id: str
    label_ru: str
    label_en: str
    intro_ru: str
    intro_en: str
    steps: tuple[LearningPathStep, ...]


@dataclass(frozen=True)
class ScenarioTaxonomy:
    service_order: tuple[str, ...]
    services: dict[str, ServiceSpec]
    learning_paths: tuple[LearningPath, ...]


def taxonomy_path(repo_root: Path | None = None) -> Path:
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[1]
    return root / "docs" / "scenarios" / "taxonomy.yaml"


def load_scenario_taxonomy(repo_root: Path | None = None) -> ScenarioTaxonomy:
    path = taxonomy_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"Нет taxonomy.yaml: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"taxonomy.yaml должен быть mapping: {path}")

    service_order_raw = raw.get("service_order")
    if not isinstance(service_order_raw, list) or not service_order_raw:
        raise ValueError("taxonomy.yaml: service_order обязателен и не может быть пустым")
    service_order = tuple(str(item) for item in service_order_raw)

    services_raw = raw.get("services")
    if not isinstance(services_raw, dict) or not services_raw:
        raise ValueError("taxonomy.yaml: services обязателен")

    services: dict[str, ServiceSpec] = {}
    for key, payload in services_raw.items():
        if not isinstance(payload, dict):
            raise ValueError(f"taxonomy.yaml: services.{key} должен быть mapping")
        tags_raw = payload.get("tags")
        if not isinstance(tags_raw, dict) or not tags_raw:
            raise ValueError(f"taxonomy.yaml: services.{key}.tags обязателен")
        tags: dict[str, TagSpec] = {}
        for tag_key, tag_payload in tags_raw.items():
            if not isinstance(tag_payload, dict):
                raise ValueError(f"taxonomy.yaml: services.{key}.tags.{tag_key} должен быть mapping")
            label_ru = tag_payload.get("label_ru")
            label_en = tag_payload.get("label_en")
            order = tag_payload.get("order")
            if not isinstance(label_ru, str) or not label_ru.strip():
                raise ValueError(f"taxonomy.yaml: services.{key}.tags.{tag_key}.label_ru обязателен")
            if not isinstance(label_en, str) or not label_en.strip():
                raise ValueError(f"taxonomy.yaml: services.{key}.tags.{tag_key}.label_en обязателен")
            if not isinstance(order, int):
                raise ValueError(f"taxonomy.yaml: services.{key}.tags.{tag_key}.order обязателен (int)")
            tags[str(tag_key)] = TagSpec(
                label_ru=label_ru.strip(),
                label_en=label_en.strip(),
                order=order,
            )
        intro_ru = payload.get("intro_ru")
        intro_en = payload.get("intro_en")
        label_ru_svc = payload.get("label_ru")
        label_en_svc = payload.get("label_en")
        if not isinstance(intro_ru, str) or not intro_ru.strip():
            raise ValueError(f"taxonomy.yaml: services.{key}.intro_ru обязателен")
        if not isinstance(intro_en, str) or not intro_en.strip():
            raise ValueError(f"taxonomy.yaml: services.{key}.intro_en обязателен")
        if not isinstance(label_ru_svc, str) or not label_ru_svc.strip():
            raise ValueError(f"taxonomy.yaml: services.{key}.label_ru обязателен")
        if not isinstance(label_en_svc, str) or not label_en_svc.strip():
            raise ValueError(f"taxonomy.yaml: services.{key}.label_en обязателен")
        featured = payload.get("featured_slug")
        featured_slug = str(featured).strip() if featured is not None else None
        if featured_slug == "":
            featured_slug = None
        services[str(key)] = ServiceSpec(
            key=str(key),
            label_ru=label_ru_svc.strip(),
            label_en=label_en_svc.strip(),
            intro_ru=intro_ru.strip(),
            intro_en=intro_en.strip(),
            featured_slug=featured_slug,
            tags=tags,
        )

    for svc in service_order:
        if svc not in services:
            raise ValueError(f"taxonomy.yaml: service_order содержит неизвестный сервис {svc!r}")

    learning_paths_raw = raw.get("learning_paths")
    if not isinstance(learning_paths_raw, list) or not learning_paths_raw:
        raise ValueError("taxonomy.yaml: learning_paths обязателен")

    learning_paths: list[LearningPath] = []
    for item in learning_paths_raw:
        if not isinstance(item, dict):
            raise ValueError("taxonomy.yaml: каждый learning_paths[] элемент — mapping")
        path_id = item.get("id")
        if not isinstance(path_id, str) or not path_id.strip():
            raise ValueError("taxonomy.yaml: learning_paths[].id обязателен")
        label_ru = item.get("label_ru")
        label_en = item.get("label_en")
        intro_ru = item.get("intro_ru")
        intro_en = item.get("intro_en")
        if not isinstance(label_ru, str) or not label_ru.strip():
            raise ValueError(f"taxonomy.yaml: learning_paths.{path_id}.label_ru обязателен")
        if not isinstance(label_en, str) or not label_en.strip():
            raise ValueError(f"taxonomy.yaml: learning_paths.{path_id}.label_en обязателен")
        if not isinstance(intro_ru, str) or not intro_ru.strip():
            raise ValueError(f"taxonomy.yaml: learning_paths.{path_id}.intro_ru обязателен")
        if not isinstance(intro_en, str) or not intro_en.strip():
            raise ValueError(f"taxonomy.yaml: learning_paths.{path_id}.intro_en обязателен")
        steps_raw = item.get("steps")
        if not isinstance(steps_raw, list) or not steps_raw:
            raise ValueError(f"taxonomy.yaml: learning_paths.{path_id}.steps обязателен")
        steps: list[LearningPathStep] = []
        for step in steps_raw:
            if not isinstance(step, dict):
                raise ValueError(f"taxonomy.yaml: learning_paths.{path_id}.steps[] — mapping")
            step_label_ru = step.get("label_ru")
            step_label_en = step.get("label_en")
            href = step.get("href")
            if not isinstance(step_label_ru, str) or not step_label_ru.strip():
                raise ValueError(f"taxonomy.yaml: learning_paths.{path_id} step.label_ru обязателен")
            if not isinstance(step_label_en, str) or not step_label_en.strip():
                raise ValueError(f"taxonomy.yaml: learning_paths.{path_id} step.label_en обязателен")
            if not isinstance(href, str) or not href.strip():
                raise ValueError(f"taxonomy.yaml: learning_paths.{path_id} step.href обязателен")
            steps.append(
                LearningPathStep(
                    label_ru=step_label_ru.strip(),
                    label_en=step_label_en.strip(),
                    href=href.strip().lstrip("/"),
                )
            )
        learning_paths.append(
            LearningPath(
                path_id=path_id.strip(),
                label_ru=label_ru.strip(),
                label_en=label_en.strip(),
                intro_ru=intro_ru.strip(),
                intro_en=intro_en.strip(),
                steps=tuple(steps),
            )
        )

    return ScenarioTaxonomy(
        service_order=service_order,
        services=services,
        learning_paths=tuple(learning_paths),
    )


def service_label(taxonomy: ScenarioTaxonomy, service: str, *, language: str) -> str:
    spec = taxonomy.services.get(service)
    if spec is None:
        return service.replace("_", " ").title()
    if language == "en":
        return spec.label_en
    return spec.label_ru


def tag_label(taxonomy: ScenarioTaxonomy, service: str, tag: str, *, language: str) -> str:
    spec = taxonomy.services.get(service)
    if spec is None:
        return tag.replace("_", " ").title()
    tag_spec = spec.tags.get(tag)
    if tag_spec is None:
        return tag.replace("_", " ").title()
    if language == "en":
        return tag_spec.label_en
    return tag_spec.label_ru


def validate_service_tag(taxonomy: ScenarioTaxonomy, service: str, tag: str) -> None:
    spec = taxonomy.services.get(service)
    if spec is None:
        raise ValueError(
            f"Неизвестный service={service!r} в @pytest.mark.scenario; "
            f"добавьте сервис в docs/scenarios/taxonomy.yaml"
        )
    if tag not in spec.tags:
        raise ValueError(
            f"Неизвестный tag={tag!r} для service={service!r}; "
            f"добавьте тег в docs/scenarios/taxonomy.yaml"
        )
