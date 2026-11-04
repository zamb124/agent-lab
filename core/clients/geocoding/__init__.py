"""Геокодинг платформы: адрес → координаты (Nominatim/OSM)."""

from core.clients.geocoding.base import GeocodedAddress, Geocoder
from core.clients.geocoding.nominatim import NominatimGeocoder

__all__ = ["GeocodedAddress", "Geocoder", "NominatimGeocoder"]
