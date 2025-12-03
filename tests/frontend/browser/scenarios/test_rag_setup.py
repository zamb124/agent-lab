"""
Сценарий: Работа с RAG - выбор провайдера, загрузка документов, поиск.

Генерирует пользовательскую документацию в docs/user_docs/user_scenarios/rag_setup/
"""

import uuid
from pathlib import Path

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestRAGSetupScenario:
    """Сценарий работы с RAG - выбор провайдера, загрузка документов, поиск"""
    
    TEST_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "agents" / "rag"
    
    async def test_rag_provider_selection(self, page: Page, e2e_base_url: str, doc_generator):
        """
        Сценарий 1: Выбор провайдера RAG.
        
        Объясняет различия между провайдерами:
        - ChromaDB: локальное хранилище, данные в РФ, экономичный
        - Agentset: облачный SaaS, удобный, дороже
        """
        doc = doc_generator("rag_provider_selection", "Выбор провайдера RAG")
        
        await page.goto(f"{e2e_base_url}/rag/")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)
        
        await doc.step(
            page,
            "Открытие раздела RAG",
            "Откройте раздел **RAG** через боковое меню или перейдите по адресу `/rag/`. "
            "Здесь вы управляете векторными хранилищами для поиска по документам."
        )
        
        # Проверяем наличие карточек провайдеров
        provider_cards = page.locator(".rag-provider-card")
        cards_count = await provider_cards.count()
        
        if cards_count >= 2:
            await doc.step(
                page,
                "Обзор провайдеров",
                "В боковой панели отображаются доступные RAG провайдеры:\n\n"
                "**ChromaDB** (LOCAL):\n"
                "- Локальное векторное хранилище\n"
                "- Данные хранятся на вашем сервере в РФ\n"
                "- Экономичное решение - без абонентской платы\n"
                "- Подходит для чувствительных данных\n\n"
                "**Agentset** (CLOUD):\n"
                "- Облачный SaaS провайдер\n"
                "- Готовая инфраструктура без настройки\n"
                "- Автоматическое масштабирование\n"
                "- Дороже, но удобнее для быстрого старта",
                ".rag-provider-cards"
            )
        
        # Выбор провайдера ChromaDB
        chromadb_card = page.locator(".rag-provider-card[data-provider='chromadb']")
        if await chromadb_card.count() > 0:
            await doc.click(
                page,
                ".rag-provider-card[data-provider='chromadb']",
                "Выбор ChromaDB",
                "Нажмите на карточку **ChromaDB** для выбора локального провайдера. "
                "Это оптимальный выбор если:\n"
                "- Важна безопасность данных (хранение в РФ)\n"
                "- Нужен контроль над инфраструктурой\n"
                "- Ограниченный бюджет"
            )
            
            await page.wait_for_timeout(500)
            
            await doc.step(
                page,
                "Провайдер выбран",
                "Выбранный провайдер отмечается подсветкой. "
                "Теперь все операции (создание неймспейсов, загрузка документов) "
                "будут выполняться через этот провайдер."
            )
        
        # Альтернативный выбор Agentset
        agentset_card = page.locator(".rag-provider-card[data-provider='agentset']")
        if await agentset_card.count() > 0:
            await doc.click(
                page,
                ".rag-provider-card[data-provider='agentset']",
                "Переключение на Agentset",
                "Для переключения на облачный провайдер нажмите **Agentset**. "
                "Рекомендуется если:\n"
                "- Нужен быстрый старт без настройки\n"
                "- Важна надежность и доступность\n"
                "- Готовы платить за удобство"
            )
            
            await page.wait_for_timeout(500)
        
        doc.save()
    
    async def test_rag_document_search(self, page: Page, e2e_base_url: str, doc_generator):
        """
        Сценарий 2: Загрузка документов и поиск.
        
        Загружает тестовые документы и выполняет поиск по ним.
        """
        doc = doc_generator("rag_document_search", "Поиск по документам в RAG")
        
        namespace_name = f"test_docs_{uuid.uuid4().hex[:6]}"
        
        # Открываем RAG Dashboard
        await page.goto(f"{e2e_base_url}/rag/")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)
        
        await doc.step(
            page,
            "Открытие RAG Dashboard",
            "Откройте раздел **RAG** для управления документами. "
            "Здесь отображаются все ваши неймспейсы (коллекции документов)."
        )
        
        # Выбираем ChromaDB провайдер
        chromadb_card = page.locator(".rag-provider-card[data-provider='chromadb']")
        if await chromadb_card.count() > 0 and not await chromadb_card.evaluate("el => el.classList.contains('active')"):
            await chromadb_card.click()
            await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Выбор провайдера",
            "Убедитесь что выбран нужный провайдер (ChromaDB для локального хранения). "
            "Провайдер определяет где будут храниться ваши документы.",
            ".rag-provider-cards"
        )
        
        # Создаём новый неймспейс
        await doc.click(
            page,
            "button:has-text('New Namespace'), .rag-btn-primary:has-text('New Namespace')",
            "Создание неймспейса",
            "Нажмите кнопку **New Namespace** для создания новой коллекции документов. "
            "Неймспейс - это изолированное хранилище для группы связанных документов."
        )
        
        await page.wait_for_selector("#create-namespace-modal.active", timeout=5000)
        await page.wait_for_timeout(300)
        
        await doc.step(
            page,
            "Форма создания неймспейса",
            "Откроется модальное окно для ввода данных неймспейса."
        )
        
        # Заполняем форму
        await doc.fill(
            page,
            "#namespace-name",
            namespace_name,
            "Ввод имени",
            "Введите **имя неймспейса**. Используйте понятное название, "
            "например: `product_docs`, `faq`, `contracts`."
        )
        
        await doc.fill(
            page,
            "#namespace-description",
            "Тестовые документы для демонстрации поиска",
            "Добавление описания",
            "Добавьте **описание** чтобы было понятно назначение коллекции."
        )
        
        # Создаём неймспейс
        create_btn = page.locator("#create-namespace-modal button:has-text('Create')")
        await doc.click(
            page,
            "#create-namespace-modal button:has-text('Create')",
            "Сохранение неймспейса",
            "Нажмите **Create** для создания неймспейса."
        )
        
        await create_btn.click()
        await page.wait_for_timeout(1500)
        
        await doc.step(
            page,
            "Неймспейс создан",
            "Неймспейс появится в списке слева и на главной панели. "
            "Теперь можно загружать в него документы."
        )
        
        # Открываем неймспейс
        namespace_item = page.locator(f".rag-namespace-item:has-text('{namespace_name}'), .rag-namespace-card:has-text('{namespace_name}')")
        if await namespace_item.count() > 0:
            await namespace_item.first.click()
            await page.wait_for_timeout(1000)
        
        await doc.step(
            page,
            "Открытие неймспейса",
            "Нажмите на неймспейс чтобы открыть его и увидеть список документов."
        )
        
        # Загружаем документы
        upload_btn = page.locator("button:has-text('Upload')")
        if await upload_btn.count() > 0:
            await doc.click(
                page,
                "button:has-text('Upload')",
                "Открытие загрузки",
                "Нажмите кнопку **Upload** для загрузки документов."
            )
            
            await page.wait_for_selector("#upload-document-modal.active", timeout=5000)
            await page.wait_for_timeout(300)
            
            await doc.step(
                page,
                "Форма загрузки файлов",
                "В модальном окне можно перетащить файлы или выбрать через проводник. "
                "Поддерживаются форматы: PDF, DOCX, TXT, XLSX, CSV, HTML, MD, JSON."
            )
            
            # Загружаем тестовые файлы
            docx_file = self.TEST_DOCS_DIR / "Анкета 09.25.docx"
            xlsx_file = self.TEST_DOCS_DIR / "all_products.xlsx"
            
            files_to_upload = []
            if docx_file.exists():
                files_to_upload.append(str(docx_file))
            if xlsx_file.exists():
                files_to_upload.append(str(xlsx_file))
            
            if files_to_upload:
                file_input = page.locator("#file-input")
                await file_input.set_input_files(files_to_upload)
                await page.wait_for_timeout(500)
                
                await doc.step(
                    page,
                    "Выбор файлов",
                    "Выбраны файлы для загрузки:\n"
                    "- **Анкета 09.25.docx** - документ Word\n"
                    "- **all_products.xlsx** - таблица Excel\n\n"
                    "Файлы отображаются в списке перед загрузкой."
                )
                
                # Загружаем файлы
                upload_submit = page.locator("#upload-btn")
                if not await upload_submit.is_disabled():
                    await doc.click(
                        page,
                        "#upload-btn",
                        "Загрузка файлов",
                        "Нажмите **Upload** для начала загрузки. "
                        "Документы будут проиндексированы и добавлены в векторное хранилище."
                    )
                    
                    await upload_submit.click()
                    await page.wait_for_timeout(3000)
            else:
                # Закрываем модалку если файлы не найдены
                close_btn = page.locator("#upload-document-modal .rag-modal-close")
                await close_btn.click()
                await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Документы загружены",
            "Загруженные документы отображаются в виде карточек. "
            "Для каждого документа показан тип файла и статус обработки."
        )
        
        # Поиск по документам
        search_input = page.locator("#global-search")
        await doc.fill(
            page,
            "#global-search",
            "Краткое описание",
            "Ввод поискового запроса",
            "Введите поисковый запрос в поле **Search across all documents**. "
            "Например: `Краткое описание` для поиска соответствующих фрагментов."
        )
        
        await page.wait_for_timeout(300)
        
        await doc.step(
            page,
            "Выполнение поиска",
            "Нажмите **Enter** для выполнения семантического поиска. "
            "RAG найдет наиболее релевантные фрагменты документов.",
            "#global-search"
        )
        
        # Выполняем поиск
        await search_input.press("Enter")
        await page.wait_for_timeout(2000)
        
        # Проверяем результаты
        search_modal = page.locator("#search-results-modal.active")
        if await search_modal.count() > 0:
            await doc.step(
                page,
                "Результаты поиска",
                "Откроется окно с результатами поиска. Для каждого результата показано:\n"
                "- Название исходного документа\n"
                "- Релевантный фрагмент текста с подсветкой\n"
                "- Процент совпадения (score)\n"
                "- Кнопка скачивания документа"
            )
            
            results = page.locator(".rag-search-result")
            results_count = await results.count()
            
            if results_count > 0:
                await doc.step(
                    page,
                    "Просмотр фрагментов",
                    f"Найдено **{results_count}** релевантных фрагментов. "
                    "Результаты отсортированы по степени соответствия запросу."
                )
            
            # Закрываем модалку результатов
            close_results = page.locator("#search-results-modal .rag-modal-close")
            await close_results.click()
            await page.wait_for_timeout(300)
        
        doc.save()
        
        # Cleanup: удаляем созданный неймспейс
        try:
            delete_btn = page.locator(f".rag-namespace-card:has-text('{namespace_name}') .rag-btn-danger")
            if await delete_btn.count() > 0:
                page.on("dialog", lambda dialog: dialog.accept())
                await delete_btn.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass


@pytest.mark.asyncio(loop_scope="session")
class TestRAGQuickScenario:
    """Быстрый тест работоспособности RAG UI без генерации документации"""
    
    async def test_rag_page_loads(self, page: Page, e2e_base_url: str):
        """RAG страница загружается корректно"""
        await page.goto(f"{e2e_base_url}/rag/")
        await page.wait_for_load_state("networkidle")
        
        # Проверяем основные элементы
        assert await page.locator(".rag-layout").count() > 0
        assert await page.locator("#page-title").count() > 0
        assert await page.locator("#global-search").count() > 0
    
    async def test_rag_provider_cards_visible(self, page: Page, e2e_base_url: str):
        """Карточки провайдеров отображаются"""
        await page.goto(f"{e2e_base_url}/rag/")
        await page.wait_for_load_state("networkidle")
        
        provider_cards = page.locator(".rag-provider-card")
        assert await provider_cards.count() >= 1
    
    async def test_rag_create_namespace_modal(self, page: Page, e2e_base_url: str):
        """Модалка создания неймспейса открывается"""
        await page.goto(f"{e2e_base_url}/rag/")
        await page.wait_for_load_state("networkidle")
        
        new_btn = page.locator("button:has-text('New Namespace')")
        if await new_btn.count() > 0:
            await new_btn.click()
            await page.wait_for_timeout(500)
            
            modal = page.locator("#create-namespace-modal.active")
            assert await modal.count() > 0
            
            # Закрываем
            close_btn = page.locator("#create-namespace-modal .rag-modal-close")
            await close_btn.click()

