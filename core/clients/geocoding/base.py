"""Контракт геокодера платформы: адрес → координаты."""

from __future__ import annotations

from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict


class GeocodedAddress(BaseModel):
    """Результат геокодинга одного адреса."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    lat: float
    lng: float
    normalized_address: str = ""
    confidence: float = 0.0
    city: str = ""
    country: str = ""


class Geocoder(Protocol):
    """Провайдер геокодинга (Nominatim, self-hosted и т.п.)."""

    async def geocode(self, query: str) -> GeocodedAddress | None:
        """Нормализовать адрес и вернуть координаты; None — не нашёл/недоступен."""
        ...
