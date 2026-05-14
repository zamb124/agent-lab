"""Тесты главной страницы без авторизации.

Ранее была ошибка: при заходе на humanitec.ru без субдомена и без авторизации
происходил редирект на /select-company. Это неправильно — главная страница
должна быть публичной (landing page).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_main_page_no_redirect_to_select_company(client: AsyncClient):
    """
    Главная страница / должна работать без редиректа для неавторизованного пользователя.

    Это основной тест на исправление бага с редиректом на /select-company.
    """
    response = await client.get("/")

    # Ожидаем успешный ответ (SPA fallback на index.html)
    assert response.status_code == 200, f"GET / вернул {response.status_code}, ожидался 200"

    # Проверяем что нет редиректа на /select-company
    assert response.status_code != 307, "GET / не должен редиректить на /select-company"
    assert response.status_code != 302, "GET / не должен редиректить"

    # В тестовом окружении может возвращаться JSON вместо HTML (SPA fallback), это нормально
    # Главное — отсутствие редиректа на /select-company
