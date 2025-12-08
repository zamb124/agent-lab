"""
Сценарий: Удаление компании.

Генерирует пользовательскую документацию в docs/user_docs/user_scenarios/delete_company/
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from playwright.async_api import Page


# Данные для второй компании
E2E_SECOND_COMPANY_ID = "e2e_delete_test_company"
E2E_SECOND_COMPANY_NAME = "Company to Delete"
E2E_SECOND_SUBDOMAIN = "e2edelete"


@pytest_asyncio.fixture(scope="function")
async def second_company_for_delete(migrated_db, e2e_test_data):
    """
    Создает вторую компанию для E2E пользователя, которую можно удалить.
    После теста очищает данные.
    """
    from apps.agents.container import get_agents_container
    from core.models import Company
    from core.db.repositories.subdomain_repository import SubdomainMapping
    
    container = get_agents_container()
    company_repo = container.company_repository
    subdomain_repo = container.subdomain_repository
    user_repo = container.user_repository
    
    user_id = e2e_test_data["user_id"]
    
    company = Company(
        company_id=E2E_SECOND_COMPANY_ID,
        subdomain=E2E_SECOND_SUBDOMAIN,
        name=E2E_SECOND_COMPANY_NAME,
        status="active",
        balance=0.0,
        created_at=datetime.now(timezone.utc),
    )
    await company_repo.set(company)
    
    await subdomain_repo.set(SubdomainMapping(
        subdomain=E2E_SECOND_SUBDOMAIN,
        company_id=E2E_SECOND_COMPANY_ID,
    ))
    
    user = await user_repo.get(user_id)
    if user:
        user.companies[E2E_SECOND_COMPANY_ID] = ["admin", "user"]
        await user_repo.set(user)
    
    yield {
        "company_id": E2E_SECOND_COMPANY_ID,
        "company_name": E2E_SECOND_COMPANY_NAME,
        "subdomain": E2E_SECOND_SUBDOMAIN,
    }
    
    # Cleanup - удаляем компанию если она осталась
    try:
        existing = await company_repo.get(E2E_SECOND_COMPANY_ID)
        if existing:
            await company_repo.delete(E2E_SECOND_COMPANY_ID)
    except Exception:
        pass
    
    try:
        await subdomain_repo.delete(E2E_SECOND_SUBDOMAIN)
    except Exception:
        pass
    
    # Восстанавливаем пользователя
    try:
        user = await user_repo.get(user_id)
        if user and E2E_SECOND_COMPANY_ID in user.companies:
            del user.companies[E2E_SECOND_COMPANY_ID]
            await user_repo.set(user)
    except Exception:
        pass


@pytest.mark.asyncio(loop_scope="session")
class TestDeleteCompanyScenario:
    """Сценарий удаления компании с генерацией документации"""

    async def test_delete_company_from_select_page(
        self,
        page: Page,
        server_url: str,
        e2e_auth_token: str,
        e2e_test_data: dict,
        second_company_for_delete: dict,
        doc_generator,
    ):
        """
        Удаление компании со страницы выбора компании.
        
        Шаги:
        1. Открыть страницу выбора компании
        2. Нажать кнопку удаления для второй компании
        3. Ввести название компании для подтверждения
        4. Подтвердить удаление
        5. Убедиться что компания удалена
        """
        doc = doc_generator("delete_company", "Удаление компании")
        
        company_name = second_company_for_delete["company_name"]
        company_id = second_company_for_delete["company_id"]
        
        # Шаг 1: Открываем страницу выбора компании (без поддомена)
        # Устанавливаем cookie для localhost
        await page.context.add_cookies([{
            "name": "auth_token",
            "value": e2e_auth_token,
            "domain": "localhost",
            "path": "/",
        }])
        
        await page.goto(f"{server_url}/frontend/select-company")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)
        
        await doc.step(
            page,
            "Страница выбора компании",
            "Откройте страницу **Выбор компании**. Здесь отображаются все компании, "
            "в которых вы являетесь участником. Для удаления компании нужна роль **admin**."
        )
        
        # Шаг 2: Находим карточку компании для удаления и нажимаем кнопку удаления
        # В шаблоне data-company-id содержит company_id (который называется subdomain в шаблоне)
        delete_button_selector = f"button.delete-company-btn[data-company-id='{company_id}']"
        
        # Ждем появления кнопки удаления
        await page.wait_for_selector(delete_button_selector, timeout=15000)
        
        await doc.click(
            page,
            delete_button_selector,
            "Кнопка удаления",
            f"Нажмите кнопку **удаления** (иконка корзины) напротив компании **{company_name}**. "
            "Кнопка доступна только для администраторов компании."
        )
        
        # Шаг 3: Ждем появления модального окна
        await page.wait_for_selector("#deleteModal.active", timeout=5000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Окно подтверждения",
            "Откроется окно подтверждения удаления. Это действие необратимо - "
            "все данные компании (боты, flows, переменные, сессии) будут удалены."
        )
        
        # Шаг 4: Вводим название компании для подтверждения
        await doc.fill(
            page,
            "#confirmNameInput",
            company_name,
            "Ввод названия",
            f"Введите название компании **{company_name}** для подтверждения удаления. "
            "Это защита от случайного удаления."
        )
        
        # Ждем пока кнопка станет активной (после ввода правильного названия)
        await page.wait_for_selector("#confirmDeleteBtn:not([disabled])", timeout=5000)
        await page.wait_for_timeout(500)
        
        # Шаг 5: Нажимаем кнопку удаления
        await doc.step(
            page,
            "Подтверждение удаления",
            "Нажмите кнопку **Удалить** для запуска процесса удаления. "
            "Удаление выполняется асинхронно и может занять несколько секунд.",
            "#confirmDeleteBtn"
        )
        
        # Кликаем на кнопку удаления
        await page.click("#confirmDeleteBtn")
        
        # Ждем завершения запроса
        await page.wait_for_timeout(3000)
        
        # Проверяем что модальное окно закрылось
        try:
            await page.wait_for_selector("#deleteModal:not(.active)", timeout=10000)
        except Exception:
            pass
        
        # Ждем пока компания удалится или перейдет в статус "deleting"
        # Удаление асинхронное через TaskIQ, поэтому проверяем несколько раз
        company_deleted_or_deleting = False
        max_attempts = 30  # ~45 секунд
        for attempt in range(max_attempts):
            await page.reload()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(500)
            
            # Проверяем есть ли компания на странице
            company_cards = page.locator(f"[data-company-id='{company_id}']")
            count = await company_cards.count()
            
            if count == 0:
                # Компания полностью удалена
                company_deleted_or_deleting = True
                break
            
            # Проверяем статус компании (если есть текст "Удаляется...")
            page_content = await page.content()
            if "Удаляется..." in page_content and company_id in page_content:
                # Компания в процессе удаления - это тоже успех
                company_deleted_or_deleting = True
                break
            
            await page.wait_for_timeout(1000)
        
        await doc.step(
            page,
            "Компания удалена",
            f"Компания **{company_name}** успешно удалена. "
            "Она больше не отображается в списке ваших компаний. "
            "Все данные компании были удалены из системы."
        )
        
        assert company_deleted_or_deleting, f"Компания {company_id} не удалена за {max_attempts} попыток"
        
        doc.save()

    async def test_delete_modal_validation(
        self,
        page: Page,
        server_url: str,
        e2e_auth_token: str,
        e2e_test_data: dict,
        second_company_for_delete: dict,
        doc_generator,
    ):
        """
        Проверка валидации в модальном окне удаления.
        Кнопка удаления неактивна пока не введено правильное название.
        """
        doc = doc_generator("delete_company_validation", "Валидация при удалении компании")
        
        company_name = second_company_for_delete["company_name"]
        company_id = second_company_for_delete["company_id"]
        
        # Устанавливаем cookie
        await page.context.add_cookies([{
            "name": "auth_token",
            "value": e2e_auth_token,
            "domain": "localhost",
            "path": "/",
        }])
        
        await page.goto(f"{server_url}/frontend/select-company")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Страница выбора",
            "Откройте страницу выбора компании."
        )
        
        # Открываем модальное окно
        delete_button_selector = f"button.delete-company-btn[data-company-id='{company_id}']"
        await page.wait_for_selector(delete_button_selector, timeout=10000)
        await page.click(delete_button_selector)
        
        await page.wait_for_selector("#deleteModal.active", timeout=5000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Кнопка неактивна",
            "Кнопка **Удалить** изначально неактивна. "
            "Это защита от случайного удаления компании."
        )
        
        # Вводим неправильное название
        await doc.fill(
            page,
            "#confirmNameInput",
            "wrong name",
            "Неправильное название",
            "Если ввести **неправильное** название компании, "
            "кнопка удаления останется неактивной."
        )
        
        # Проверяем что кнопка все еще неактивна
        confirm_btn = page.locator("#confirmDeleteBtn")
        is_disabled = await confirm_btn.is_disabled()
        assert is_disabled, "Кнопка должна быть неактивна при неправильном названии"
        
        # Очищаем и вводим правильное название
        await page.fill("#confirmNameInput", "")
        await doc.fill(
            page,
            "#confirmNameInput",
            company_name,
            "Правильное название",
            f"Введите **точное** название компании: **{company_name}**. "
            "Кнопка станет активной."
        )
        
        # Проверяем что кнопка стала активной
        is_disabled = await confirm_btn.is_disabled()
        assert not is_disabled, "Кнопка должна быть активна при правильном названии"
        
        # Закрываем модальное окно без удаления
        await page.click("button.modal-btn.cancel")
        
        doc.save()

