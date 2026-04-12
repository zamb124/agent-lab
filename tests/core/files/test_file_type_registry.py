"""Тесты инвариантов реестра типов файлов и API-эндпоинта."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from core.files.types import (
    ALL_CATEGORIES,
    FILE_TYPE_REGISTRY,
    FileCategory,
    FileTypeEntry,
    accept_string_for,
    ext_to_category,
    ext_to_mime,
    extensions_for,
    mime_to_category,
    mimes_for,
)
from core.app.file_types_route import register_platform_file_types_route


class TestRegistryInvariants:
    """Структурные инварианты Python-реестра."""

    def test_no_duplicate_extensions(self) -> None:
        seen: set[str] = set()
        for entry in FILE_TYPE_REGISTRY:
            assert entry.extension not in seen, (
                f"Дублирующееся расширение: {entry.extension}"
            )
            seen.add(entry.extension)

    def test_every_entry_has_at_least_one_mime(self) -> None:
        for entry in FILE_TYPE_REGISTRY:
            assert len(entry.mime_types) >= 1, (
                f"{entry.extension} не имеет ни одного MIME"
            )

    def test_all_categories_covered(self) -> None:
        covered = {entry.category for entry in FILE_TYPE_REGISTRY}
        for cat in FileCategory:
            assert cat in covered, f"Категория {cat} не покрыта ни одним расширением"

    def test_extensions_start_with_dot(self) -> None:
        for entry in FILE_TYPE_REGISTRY:
            assert entry.extension.startswith("."), (
                f"Расширение без точки: {entry.extension}"
            )

    def test_all_entries_are_frozen(self) -> None:
        for entry in FILE_TYPE_REGISTRY:
            assert isinstance(entry, FileTypeEntry)
            with pytest.raises(AttributeError):
                entry.extension = ".changed"

    def test_all_categories_in_all_categories_tuple(self) -> None:
        for cat in FileCategory:
            assert cat in ALL_CATEGORIES


class TestHelpers:
    """Проверка хелпер-функций реестра."""

    def test_extensions_for_returns_only_matching(self) -> None:
        pdf_exts = extensions_for(FileCategory.PDF)
        assert ".pdf" in pdf_exts
        assert ".txt" not in pdf_exts

    def test_extensions_for_multiple_categories(self) -> None:
        exts = extensions_for(FileCategory.PDF, FileCategory.TEXT)
        assert ".pdf" in exts
        assert ".txt" in exts
        assert ".mp3" not in exts

    def test_mimes_for(self) -> None:
        mimes = mimes_for(FileCategory.IMAGE)
        assert "image/png" in mimes
        assert "image/jpeg" in mimes
        assert "audio/mpeg" not in mimes

    def test_ext_to_mime_known(self) -> None:
        assert ext_to_mime(".pdf") == "application/pdf"
        assert ext_to_mime(".png") == "image/png"

    def test_ext_to_mime_unknown(self) -> None:
        assert ext_to_mime(".xyz_nonexistent") == "application/octet-stream"

    def test_ext_to_category(self) -> None:
        assert ext_to_category(".mp3") == FileCategory.AUDIO
        assert ext_to_category(".docx") == FileCategory.OFFICE_DOC
        assert ext_to_category(".xyz_nonexistent") is None

    def test_mime_to_category(self) -> None:
        assert mime_to_category("application/pdf") == FileCategory.PDF
        assert mime_to_category("image/png") == FileCategory.IMAGE
        assert mime_to_category("something/unknown") is None

    def test_mime_to_category_strips_params(self) -> None:
        assert mime_to_category("text/plain; charset=utf-8") == FileCategory.TEXT

    def test_accept_string_for_includes_extensions(self) -> None:
        accept = accept_string_for(FileCategory.PDF)
        assert ".pdf" in accept

    def test_accept_string_for_image_has_wildcard(self) -> None:
        accept = accept_string_for(FileCategory.IMAGE)
        assert "image/*" in accept
        assert ".png" in accept

    def test_accept_string_for_audio_video_wildcards(self) -> None:
        accept = accept_string_for(FileCategory.AUDIO, FileCategory.VIDEO)
        assert "audio/*" in accept
        assert "video/*" in accept


class TestApiEndpoint:
    """Тесты GET /api/platform/file-types."""

    @pytest.fixture
    def app(self) -> FastAPI:
        app = FastAPI()
        register_platform_file_types_route(app)
        return app

    @pytest.mark.asyncio
    async def test_returns_categories_and_registry(self, app: FastAPI) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/platform/file-types")
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data
        assert "registry" in data
        assert isinstance(data["categories"], list)
        assert isinstance(data["registry"], list)

    @pytest.mark.asyncio
    async def test_categories_match_python_enum(self, app: FastAPI) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/platform/file-types")
        data = resp.json()
        api_categories = set(data["categories"])
        python_categories = {c.value for c in FileCategory}
        assert api_categories == python_categories

    @pytest.mark.asyncio
    async def test_registry_count_matches(self, app: FastAPI) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/platform/file-types")
        data = resp.json()
        assert len(data["registry"]) == len(FILE_TYPE_REGISTRY)

    @pytest.mark.asyncio
    async def test_registry_entry_shape(self, app: FastAPI) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/platform/file-types")
        data = resp.json()
        for entry in data["registry"]:
            assert "extension" in entry
            assert "mime_types" in entry
            assert "category" in entry
            assert isinstance(entry["mime_types"], list)
            assert len(entry["mime_types"]) >= 1
            assert entry["extension"].startswith(".")

    @pytest.mark.asyncio
    async def test_cache_control_header(self, app: FastAPI) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/platform/file-types")
        assert "max-age=3600" in resp.headers.get("cache-control", "")
