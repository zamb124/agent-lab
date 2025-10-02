"""
AmoCRM API клиент для работы с основным API (сделки, контакты, задачи и т.д.)

ВАЖНО: Chat API в AmoCRM работает через webhook'и и scope,
а не через обычные REST эндпоинты. Для работы с чатами нужна
отдельная интеграция через Chat API с использованием scope_id.

Этот клиент работает с основным API v4 AmoCRM.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx
from pydantic import BaseModel

from ...core.config import settings

logger = logging.getLogger(__name__)


# Глобальный кеш для singleton клиентов
_client_cache: Dict[tuple, "AmoCRMClient"] = {}

# Маппинг subdomain -> access_token
# TODO: Перенести в настройки или базу данных для продакшена
_subdomain_to_token: Dict[str, str] = {}


class AmoCRMLead(BaseModel):
    """Модель сделки в AmoCRM"""

    id: int
    name: str
    price: Optional[int] = None
    responsible_user_id: Optional[int] = None
    status_id: Optional[int] = None
    pipeline_id: Optional[int] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


class AmoCRMContact(BaseModel):
    """Модель контакта в AmoCRM"""

    id: int
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    responsible_user_id: Optional[int] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


class AmoCRMClient:
    """
    Полнофункциональный клиент для работы с AmoCRM API v4

    Поддерживает все основные разделы API:

    📌 Основные сущности (CRUD):
    - Сделки (leads): получение, создание, обновление
    - Контакты (contacts): получение, создание, обновление
    - Компании (companies): получение, создание, обновление
    - Покупатели (customers): получение, создание, обновление, транзакции, сегменты
    - Задачи (tasks): получение, создание, обновление, завершение

    📊 Структура и настройки:
    - Воронки и статусы (pipelines): получение воронок и их статусов
    - Каталоги (catalogs): получение каталогов и элементов, создание/обновление товаров
    - Кастомные поля (custom_fields): получение полей для всех типов сущностей

    🔗 Связи и примечания:
    - Связи сущностей (entity links): получение, привязка и отвязка связей
    - Примечания (notes): получение и создание примечаний к сущностям
    - Беседы (talks): получение и закрытие бесед из мессенджеров

    📥 Неразобранное:
    - Неразобранные заявки (unsorted): получение, принятие, отклонение и привязка

    🔌 Интеграции и автоматизация:
    - Вебхуки (webhooks): получение, создание и удаление подписок
    - Виджеты (widgets): получение установленных виджетов
    - Звонки (calls): добавление информации о звонках

    📋 Дополнительно:
    - События (events): получение истории изменений
    - Источники (sources): получение списка источников
    - Роли (roles): получение ролей и прав пользователей
    - Короткие ссылки (short_links): создание коротких ссылок
    - Пользователи и аккаунт (users, account): информация об аккаунте и пользователях

    Примечание: Полноценный Chat API требует отдельной интеграции с webhook'ами (см. AmoCRMChatClient)
    """

    def __init__(
        self,
        subdomain: str,
        access_token: str,
    ):
        """
        Инициализация клиента AmoCRM

        Args:
            subdomain: Поддомен вашего аккаунта (например, 'mycompany')
            access_token: Токен доступа OAuth 2.0
        """
        self.subdomain = subdomain
        self.base_url = f"https://{subdomain}.amocrm.ru/api/v4"

        self.access_token = access_token

        self._client: Optional[httpx.AsyncClient] = None

        logger.info(f"AmoCRM клиент инициализирован для поддомена: {subdomain}")

    def _get_client(self) -> httpx.AsyncClient:
        """Получает или создает HTTP клиент"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self):
        """Закрывает HTTP клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ========== РАБОТА СО СДЕЛКАМИ (LEADS) ==========

    async def get_leads(self, limit: int = 50, page: int = 1, query: Optional[str] = None, with_contacts: bool = False) -> List[Dict[str, Any]]:
        """
        Получает список сделок

        Args:
            limit: Количество сделок на странице (макс. 250)
            page: Номер страницы
            query: Поисковый запрос
            with_contacts: Включить связанные контакты

        Returns:
            Список сделок
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if query:
            params["query"] = query

        if with_contacts:
            params["with"] = "contacts"

        try:
            response = await client.get(f"{self.base_url}/leads", params=params)
            response.raise_for_status()

            if response.status_code == 204:
                raise httpx.HTTPStatusError(
                    "Получен пустой ответ (204 No Content) при запросе списка сделок",
                    request=response.request,
                    response=response,
                )

            data = response.json()
            leads = data.get("_embedded", {}).get("leads", [])

            logger.info(f"Получено {len(leads)} сделок")
            return leads

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить сделки из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_lead(self, lead_id: int, with_param: Optional[str] = None) -> Dict[str, Any]:
        """
        Получает сделку по ID

        Args:
            lead_id: ID сделки
            with_param: Дополнительные данные ("contacts", "catalog_elements", "loss_reason", "source_id", "is_price_modified_by_robot")

        Returns:
            Данные сделки
        """
        client = self._get_client()

        params = {}
        if with_param:
            params["with"] = with_param

        try:
            response = await client.get(f"{self.base_url}/leads/{lead_id}", params=params)
            response.raise_for_status()

            logger.info(f"Получена сделка {lead_id}")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить сделку {lead_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает новую сделку

        Args:
            lead_data: Данные сделки (name обязательно, опционально: price, status_id, pipeline_id, created_by, custom_fields_values, _embedded и т.д.)

        Returns:
            Данные созданной сделки
        """
        client = self._get_client()

        payload = [lead_data]

        try:
            response = await client.post(f"{self.base_url}/leads", json=payload)
            response.raise_for_status()

            result = response.json()
            created = result.get("_embedded", {}).get("leads", [])
            logger.info(f"Создана сделка: {created}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать сделку в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_leads_complex(self, leads_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Создает несколько сделок с возможностью привязки контактов и компаний (complex метод)

        Args:
            leads_data: Список данных сделок с возможностью указать _embedded.contacts и _embedded.companies

        Returns:
            Результат создания сделок
        """
        client = self._get_client()

        try:
            response = await client.post(f"{self.base_url}/leads/complex", json=leads_data)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Создано сделок (complex): {len(leads_data)}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать сделки (complex) в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def update_lead(self, lead_id: int, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет сделку

        Args:
            lead_id: ID сделки
            lead_data: Обновляемые данные сделки

        Returns:
            Обновленные данные сделки
        """
        client = self._get_client()

        lead_data["id"] = lead_id
        payload = [lead_data]

        try:
            response = await client.patch(f"{self.base_url}/leads", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Обновлена сделка {lead_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось обновить сделку {lead_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С КОНТАКТАМИ (CONTACTS) ==========

    async def get_contacts(self, limit: int = 50, page: int = 1, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получает список контактов

        Args:
            limit: Количество контактов на странице (макс. 250)
            page: Номер страницы
            query: Поисковый запрос

        Returns:
            Список контактов
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if query:
            params["query"] = query

        try:
            response = await client.get(f"{self.base_url}/contacts", params=params)
            response.raise_for_status()

            data = response.json()
            contacts = data.get("_embedded", {}).get("contacts", [])

            logger.info(f"Получено {len(contacts)} контактов")
            return contacts

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить контакты из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_contact(self, contact_id: int, with_param: Optional[str] = None) -> Dict[str, Any]:
        """
        Получает контакт по ID

        Args:
            contact_id: ID контакта
            with_param: Дополнительные данные ("leads", "customers", "catalog_elements")

        Returns:
            Данные контакта
        """
        client = self._get_client()

        params = {}
        if with_param:
            params["with"] = with_param

        try:
            response = await client.get(f"{self.base_url}/contacts/{contact_id}", params=params)
            response.raise_for_status()

            logger.info(f"Получен контакт {contact_id}")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить контакт {contact_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает новый контакт

        Args:
            contact_data: Данные контакта (name обязательно, опционально: first_name, last_name, responsible_user_id, custom_fields_values и т.д.)

        Returns:
            Данные созданного контакта
        """
        client = self._get_client()

        payload = [contact_data]

        try:
            response = await client.post(f"{self.base_url}/contacts", json=payload)
            response.raise_for_status()

            result = response.json()
            created = result.get("_embedded", {}).get("contacts", [])
            logger.info(f"Создан контакт: {created}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать контакт в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_contacts_complex(self, contacts_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Создает несколько контактов с возможностью привязки сделок и компаний (complex метод)

        Args:
            contacts_data: Список данных контактов с возможностью указать _embedded.leads и _embedded.companies

        Returns:
            Результат создания контактов
        """
        client = self._get_client()

        try:
            response = await client.post(f"{self.base_url}/contacts/complex", json=contacts_data)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Создано контактов (complex): {len(contacts_data)}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать контакты (complex) в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def update_contact(self, contact_id: int, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет контакт

        Args:
            contact_id: ID контакта
            contact_data: Обновляемые данные контакта

        Returns:
            Обновленные данные контакта
        """
        client = self._get_client()

        contact_data["id"] = contact_id
        payload = [contact_data]

        try:
            response = await client.patch(f"{self.base_url}/contacts", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Обновлен контакт {contact_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось обновить контакт {contact_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С КОМПАНИЯМИ (COMPANIES) ==========

    async def get_companies(self, limit: int = 50, page: int = 1, query: Optional[str] = None, with_param: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получает список компаний

        Args:
            limit: Количество компаний на странице (макс. 250)
            page: Номер страницы
            query: Поисковый запрос
            with_param: Дополнительные данные ("leads", "contacts", "customers", "catalog_elements")

        Returns:
            Список компаний
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if query:
            params["query"] = query

        if with_param:
            params["with"] = with_param

        try:
            response = await client.get(f"{self.base_url}/companies", params=params)
            response.raise_for_status()

            data = response.json()
            companies = data.get("_embedded", {}).get("companies", [])

            logger.info(f"Получено {len(companies)} компаний")
            return companies

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить компании из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_company(self, company_id: int, with_param: Optional[str] = None) -> Dict[str, Any]:
        """
        Получает компанию по ID

        Args:
            company_id: ID компании
            with_param: Дополнительные данные ("leads", "contacts", "customers", "catalog_elements")

        Returns:
            Данные компании
        """
        client = self._get_client()

        params = {}
        if with_param:
            params["with"] = with_param

        try:
            response = await client.get(f"{self.base_url}/companies/{company_id}", params=params)
            response.raise_for_status()

            logger.info(f"Получена компания {company_id}")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить компанию {company_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_company(self, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает новую компанию

        Args:
            company_data: Данные компании (name обязательно, опционально: responsible_user_id, custom_fields_values и т.д.)

        Returns:
            Данные созданной компании
        """
        client = self._get_client()

        payload = [company_data]

        try:
            response = await client.post(f"{self.base_url}/companies", json=payload)
            response.raise_for_status()

            result = response.json()
            created = result.get("_embedded", {}).get("companies", [])
            logger.info(f"Создана компания: {created}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать компанию в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def update_company(self, company_id: int, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет компанию

        Args:
            company_id: ID компании
            company_data: Обновляемые данные компании

        Returns:
            Обновленные данные компании
        """
        client = self._get_client()

        company_data["id"] = company_id
        payload = [company_data]

        try:
            response = await client.patch(f"{self.base_url}/companies", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Обновлена компания {company_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось обновить компанию {company_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С ЗАДАЧАМИ (TASKS) ==========

    async def get_tasks(
        self, limit: int = 50, page: int = 1, filter_entity_type: Optional[str] = None, filter_entity_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Получает список задач

        Args:
            limit: Количество задач на странице (макс. 250)
            page: Номер страницы
            filter_entity_type: Фильтр по типу сущности ("leads", "contacts", "companies")
            filter_entity_id: ID сущности для фильтра

        Returns:
            Список задач
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if filter_entity_type:
            params["filter[entity_type]"] = filter_entity_type

        if filter_entity_id:
            params["filter[entity_id]"] = filter_entity_id

        try:
            response = await client.get(f"{self.base_url}/tasks", params=params)
            response.raise_for_status()

            data = response.json()
            tasks = data.get("_embedded", {}).get("tasks", [])

            logger.info(f"Получено {len(tasks)} задач")
            return tasks

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить задачи из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает новую задачу

        Args:
            task_data: Данные задачи (text обязательно, опционально: complete_till, entity_id, entity_type, task_type_id, responsible_user_id и т.д.)

        Returns:
            Данные созданной задачи
        """
        client = self._get_client()

        payload = [task_data]

        try:
            response = await client.post(f"{self.base_url}/tasks", json=payload)
            response.raise_for_status()

            result = response.json()
            created = result.get("_embedded", {}).get("tasks", [])
            logger.info(f"Создана задача: {created}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать задачу в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def update_task(self, task_id: int, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет задачу

        Args:
            task_id: ID задачи
            task_data: Обновляемые данные задачи

        Returns:
            Обновленные данные задачи
        """
        client = self._get_client()

        task_data["id"] = task_id
        payload = [task_data]

        try:
            response = await client.patch(f"{self.base_url}/tasks", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Обновлена задача {task_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось обновить задачу {task_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def complete_task(self, task_id: int, result_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Завершает задачу

        Args:
            task_id: ID задачи
            result_text: Текст результата выполнения задачи

        Returns:
            Данные завершенной задачи
        """
        task_data = {
            "id": task_id,
            "is_completed": True,
        }

        if result_text:
            task_data["result"] = {"text": result_text}

        return await self.update_task(task_id, task_data)

    # ========== РАБОТА С СОБЫТИЯМИ (EVENTS) ==========

    async def get_events(self, limit: int = 50, page: int = 1, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получает список событий (история изменений)

        Args:
            limit: Количество событий на странице (макс. 100)
            page: Номер страницы
            filter_type: Фильтр по типу события

        Returns:
            Список событий
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 100),
            "page": page,
        }

        if filter_type:
            params["filter[type]"] = filter_type

        try:
            response = await client.get(f"{self.base_url}/events", params=params)
            response.raise_for_status()

            data = response.json()
            events = data.get("_embedded", {}).get("events", [])

            logger.info(f"Получено {len(events)} событий")
            return events

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить события из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С ПОКУПАТЕЛЯМИ (CUSTOMERS) ==========

    async def get_customers(
        self,
        limit: int = 50,
        page: int = 1,
        query: Optional[str] = None,
        filter_next_date_from: Optional[int] = None,
        filter_next_date_to: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает список покупателей

        Args:
            limit: Количество покупателей на странице (макс. 250)
            page: Номер страницы
            query: Поисковый запрос
            filter_next_date_from: Фильтр по дате следующей покупки (timestamp от)
            filter_next_date_to: Фильтр по дате следующей покупки (timestamp до)

        Returns:
            Список покупателей
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if query:
            params["query"] = query

        if filter_next_date_from:
            params["filter[next_date][from]"] = filter_next_date_from

        if filter_next_date_to:
            params["filter[next_date][to]"] = filter_next_date_to

        try:
            response = await client.get(f"{self.base_url}/customers", params=params)
            response.raise_for_status()

            data = response.json()
            customers = data.get("_embedded", {}).get("customers", [])

            logger.info(f"Получено {len(customers)} покупателей")
            return customers

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить покупателей из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_customer(self, customer_id: int) -> Dict[str, Any]:
        """
        Получает покупателя по ID

        Args:
            customer_id: ID покупателя

        Returns:
            Данные покупателя
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/customers/{customer_id}")
            response.raise_for_status()

            logger.info(f"Получен покупатель {customer_id}")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить покупателя {customer_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает нового покупателя

        Args:
            customer_data: Данные покупателя (name обязательно, опционально: next_date, responsible_user_id, custom_fields_values и т.д.)

        Returns:
            Данные созданного покупателя
        """
        client = self._get_client()

        payload = [customer_data]

        try:
            response = await client.post(f"{self.base_url}/customers", json=payload)
            response.raise_for_status()

            result = response.json()
            created = result.get("_embedded", {}).get("customers", [])
            logger.info(f"Создан покупатель: {created}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать покупателя в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def update_customer(self, customer_id: int, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет покупателя

        Args:
            customer_id: ID покупателя
            customer_data: Обновляемые данные покупателя

        Returns:
            Обновленные данные покупателя
        """
        client = self._get_client()

        customer_data["id"] = customer_id
        payload = [customer_data]

        try:
            response = await client.patch(f"{self.base_url}/customers", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Обновлен покупатель {customer_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось обновить покупателя {customer_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_customer_transactions(
        self,
        customer_id: int,
        limit: int = 50,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Получает транзакции покупателя

        Args:
            customer_id: ID покупателя
            limit: Количество транзакций на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список транзакций покупателя
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/customers/{customer_id}/transactions", params=params)
            response.raise_for_status()

            data = response.json()
            transactions = data.get("_embedded", {}).get("transactions", [])

            logger.info(f"Получено {len(transactions)} транзакций покупателя {customer_id}")
            return transactions

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить транзакции покупателя {customer_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_customer_transaction(self, customer_id: int, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает транзакцию для покупателя

        Args:
            customer_id: ID покупателя
            transaction_data: Данные транзакции (price обязательно, опционально: comment, created_at и т.д.)

        Returns:
            Данные созданной транзакции
        """
        client = self._get_client()

        transaction_data["customer_id"] = customer_id
        payload = [transaction_data]

        try:
            response = await client.post(f"{self.base_url}/customers/{customer_id}/transactions", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Создана транзакция для покупателя {customer_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать транзакцию для покупателя {customer_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_customer_segments(self, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает список сегментов покупателей

        Args:
            limit: Количество сегментов на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список сегментов покупателей
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/customers/segments", params=params)
            response.raise_for_status()

            data = response.json()
            segments = data.get("_embedded", {}).get("segments", [])

            logger.info(f"Получено {len(segments)} сегментов покупателей")
            return segments

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить сегменты покупателей из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С КАТАЛОГАМИ (CATALOGS) ==========

    async def get_catalogs(self, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает список каталогов

        Args:
            limit: Количество каталогов на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список каталогов
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/catalogs", params=params)
            response.raise_for_status()

            data = response.json()
            catalogs = data.get("_embedded", {}).get("catalogs", [])

            logger.info(f"Получено {len(catalogs)} каталогов")
            return catalogs

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить каталоги из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_catalog(self, catalog_id: int) -> Dict[str, Any]:
        """
        Получает каталог по ID

        Args:
            catalog_id: ID каталога

        Returns:
            Данные каталога
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/catalogs/{catalog_id}")
            response.raise_for_status()

            logger.info(f"Получен каталог {catalog_id}")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить каталог {catalog_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_catalog_elements(self, catalog_id: int, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает элементы каталога

        Args:
            catalog_id: ID каталога
            limit: Количество элементов на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список элементов каталога
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/catalogs/{catalog_id}/elements", params=params)
            response.raise_for_status()

            data = response.json()
            elements = data.get("_embedded", {}).get("elements", [])

            logger.info(f"Получено {len(elements)} элементов каталога {catalog_id}")
            return elements

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить элементы каталога {catalog_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_catalog_element(self, catalog_id: int, element_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает элемент каталога (товар)

        Args:
            catalog_id: ID каталога
            element_data: Данные элемента (name обязательно, опционально: custom_fields_values и т.д.)

        Returns:
            Данные созданного элемента
        """
        client = self._get_client()

        payload = [element_data]

        try:
            response = await client.post(f"{self.base_url}/catalogs/{catalog_id}/elements", json=payload)
            response.raise_for_status()

            result = response.json()
            created = result.get("_embedded", {}).get("elements", [])
            logger.info(f"Создан элемент каталога {catalog_id}: {created}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать элемент каталога {catalog_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def update_catalog_element(self, catalog_id: int, element_id: int, element_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет элемент каталога

        Args:
            catalog_id: ID каталога
            element_id: ID элемента
            element_data: Обновляемые данные элемента

        Returns:
            Обновленные данные элемента
        """
        client = self._get_client()

        element_data["id"] = element_id
        payload = [element_data]

        try:
            response = await client.patch(f"{self.base_url}/catalogs/{catalog_id}/elements", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Обновлен элемент {element_id} каталога {catalog_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось обновить элемент {element_id} каталога {catalog_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С ВОРОНКАМИ (PIPELINES) ==========

    async def get_pipelines(self, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает список воронок

        Args:
            limit: Количество воронок на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список воронок
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/leads/pipelines", params=params)
            response.raise_for_status()

            data = response.json()
            pipelines = data.get("_embedded", {}).get("pipelines", [])

            logger.info(f"Получено {len(pipelines)} воронок")
            return pipelines

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить воронки из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_pipeline(self, pipeline_id: int) -> Dict[str, Any]:
        """
        Получает воронку по ID

        Args:
            pipeline_id: ID воронки

        Returns:
            Данные воронки со статусами
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/leads/pipelines/{pipeline_id}")
            response.raise_for_status()

            logger.info(f"Получена воронка {pipeline_id}")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить воронку {pipeline_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_pipeline_statuses(self, pipeline_id: int) -> List[Dict[str, Any]]:
        """
        Получает статусы воронки

        Args:
            pipeline_id: ID воронки

        Returns:
            Список статусов воронки
        """
        pipeline = await self.get_pipeline(pipeline_id)
        statuses = pipeline.get("_embedded", {}).get("statuses", [])

        logger.info(f"Получено {len(statuses)} статусов воронки {pipeline_id}")
        return statuses

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    async def get_account_info(self, with_amojo_id: bool = False) -> Dict[str, Any]:
        """
        Получает информацию об аккаунте

        Args:
            with_amojo_id: Включить amojo_id аккаунта (необходимо для Chat API)

        Returns:
            Информация об аккаунте
        """
        client = self._get_client()

        params = {}
        if with_amojo_id:
            params["with"] = "amojo_id"

        try:
            response = await client.get(f"{self.base_url}/account", params=params)
            response.raise_for_status()

            logger.info("Получена информация об аккаунте")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить информацию об аккаунте AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_users(self, limit: int = 50, page: int = 1, with_amojo_id: bool = False) -> List[Dict[str, Any]]:
        """
        Получает список пользователей аккаунта

        Args:
            limit: Количество пользователей на странице (макс. 250)
            page: Номер страницы
            with_amojo_id: Включить amojo_id пользователей (необходимо для Chat API)

        Returns:
            Список пользователей
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if with_amojo_id:
            params["with"] = "amojo_id"

        try:
            response = await client.get(f"{self.base_url}/users", params=params)
            response.raise_for_status()

            data = response.json()
            users = data.get("_embedded", {}).get("users", [])

            logger.info(f"Получено {len(users)} пользователей")
            return users

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить пользователей из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С ПРИМЕЧАНИЯМИ (NOTES) ==========

    async def get_notes(self, entity_type: str, entity_id: int, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает список примечаний/комментариев к сущности (сделка/контакт)

        Args:
            entity_type: Тип сущности ("leads", "contacts", "companies", "customers")
            entity_id: ID сущности
            limit: Количество примечаний на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список примечаний
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
            "filter[entity_type]": entity_type,
            "filter[entity_id]": entity_id,
        }

        try:
            response = await client.get(f"{self.base_url}/{entity_type}/{entity_id}/notes", params=params)
            response.raise_for_status()

            data = response.json()
            notes = data.get("_embedded", {}).get("notes", [])

            logger.info(f"Получено {len(notes)} примечаний для {entity_type}:{entity_id}")
            return notes

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить примечания из AmoCRM (subdomain={self.subdomain}, {entity_type}:{entity_id}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_note(
        self, entity_type: str, entity_id: int, note_type: str, text: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Создает примечание/комментарий к сущности

        Args:
            entity_type: Тип сущности ("leads", "contacts", "companies")
            entity_id: ID сущности
            note_type: Тип примечания ("common", "call_in", "call_out", "extended_service_message")
            text: Текст примечания
            params: Дополнительные параметры примечания

        Returns:
            Данные созданного примечания
        """
        client = self._get_client()

        note_data = {
            "entity_id": entity_id,
            "note_type": note_type,
            "params": {"text": text},
        }

        if params:
            note_data["params"].update(params)

        payload = [note_data]

        try:
            response = await client.post(f"{self.base_url}/{entity_type}/notes", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Создано примечание для {entity_type}:{entity_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать примечание в AmoCRM (subdomain={self.subdomain}, {entity_type}:{entity_id}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С КАСТОМНЫМИ ПОЛЯМИ (CUSTOM FIELDS) ==========

    async def get_custom_fields(self, entity_type: str, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает список кастомных полей для типа сущности

        Args:
            entity_type: Тип сущности ("leads", "contacts", "companies", "customers", "segments", "catalogs")
            limit: Количество полей на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список кастомных полей
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/{entity_type}/custom_fields", params=params)
            response.raise_for_status()

            data = response.json()
            fields = data.get("_embedded", {}).get("custom_fields", [])

            logger.info(f"Получено {len(fields)} кастомных полей для {entity_type}")
            return fields

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить кастомные поля для {entity_type} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА СО СВЯЗЯМИ СУЩНОСТЕЙ (ENTITY LINKS) ==========

    async def get_entity_links(self, entity_type: str, entity_id: int) -> List[Dict[str, Any]]:
        """
        Получает связи сущности с другими сущностями

        Args:
            entity_type: Тип сущности ("leads", "contacts", "companies", "customers")
            entity_id: ID сущности

        Returns:
            Список связей сущности
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/{entity_type}/{entity_id}/links")
            response.raise_for_status()

            data = response.json()
            links = data.get("_embedded", {}).get("links", [])

            logger.info(f"Получено {len(links)} связей для {entity_type}:{entity_id}")
            return links

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить связи для {entity_type}:{entity_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def link_entities(self, entity_type: str, entity_id: int, links_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Привязывает сущности друг к другу

        Args:
            entity_type: Тип основной сущности ("leads", "contacts", "companies", "customers")
            entity_id: ID основной сущности
            links_data: Список привязываемых сущностей [{"to_entity_id": 123, "to_entity_type": "contacts"}]

        Returns:
            Результат привязки
        """
        client = self._get_client()

        payload = links_data

        try:
            response = await client.post(f"{self.base_url}/{entity_type}/{entity_id}/link", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Привязаны сущности к {entity_type}:{entity_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось привязать сущности к {entity_type}:{entity_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def unlink_entities(self, entity_type: str, entity_id: int, links_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Отвязывает сущности друг от друга

        Args:
            entity_type: Тип основной сущности ("leads", "contacts", "companies", "customers")
            entity_id: ID основной сущности
            links_data: Список отвязываемых сущностей [{"to_entity_id": 123, "to_entity_type": "contacts"}]

        Returns:
            Результат отвязки
        """
        client = self._get_client()

        payload = links_data

        try:
            response = await client.post(f"{self.base_url}/{entity_type}/{entity_id}/unlink", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Отвязаны сущности от {entity_type}:{entity_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось отвязать сущности от {entity_type}:{entity_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С НЕРАЗОБРАННЫМ (UNSORTED) ==========

    async def get_unsorted(
        self,
        limit: int = 50,
        page: int = 1,
        filter_category: Optional[str] = None,
        filter_pipeline_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает список неразобранных заявок

        Args:
            limit: Количество заявок на странице (макс. 250)
            page: Номер страницы
            filter_category: Фильтр по категории ("sip", "mail", "forms", "chats")
            filter_pipeline_id: ID воронки для фильтрации

        Returns:
            Список неразобранных заявок
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if filter_category:
            params["filter[category]"] = filter_category

        if filter_pipeline_id:
            params["filter[pipeline_id]"] = filter_pipeline_id

        try:
            response = await client.get(f"{self.base_url}/leads/unsorted", params=params)
            response.raise_for_status()

            data = response.json()
            unsorted = data.get("_embedded", {}).get("unsorted", [])

            logger.info(f"Получено {len(unsorted)} неразобранных заявок")
            return unsorted

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить неразобранные заявки из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def accept_unsorted(self, unsorted_id: str, user_id: int, status_id: int) -> Dict[str, Any]:
        """
        Принимает неразобранную заявку (создает сделку)

        Args:
            unsorted_id: UID неразобранной заявки
            user_id: ID ответственного пользователя
            status_id: ID статуса сделки

        Returns:
            Данные созданной сделки
        """
        client = self._get_client()

        payload = {
            "user_id": user_id,
            "status_id": status_id,
        }

        try:
            response = await client.post(f"{self.base_url}/leads/unsorted/{unsorted_id}/accept", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Принята неразобранная заявка {unsorted_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось принять неразобранную заявку {unsorted_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def decline_unsorted(self, unsorted_id: str, user_id: int) -> Dict[str, Any]:
        """
        Отклоняет неразобранную заявку

        Args:
            unsorted_id: UID неразобранной заявки
            user_id: ID пользователя, отклоняющего заявку

        Returns:
            Результат отклонения
        """
        client = self._get_client()

        payload = {
            "user_id": user_id,
        }

        try:
            response = await client.post(f"{self.base_url}/leads/unsorted/{unsorted_id}/decline", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Отклонена неразобранная заявка {unsorted_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось отклонить неразобранную заявку {unsorted_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def link_unsorted(self, unsorted_id: str, link_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Привязывает неразобранную заявку к существующей сущности

        Args:
            unsorted_id: UID неразобранной заявки
            link_data: Данные привязки {"link": {"entity_id": 123, "entity_type": "leads"}}

        Returns:
            Результат привязки
        """
        client = self._get_client()

        try:
            response = await client.post(f"{self.base_url}/leads/unsorted/{unsorted_id}/link", json=link_data)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Привязана неразобранная заявка {unsorted_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось привязать неразобранную заявку {unsorted_id} в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С ВЕБХУКАМИ (WEBHOOKS) ==========

    async def get_webhooks(self) -> List[Dict[str, Any]]:
        """
        Получает список подписок на вебхуки

        Returns:
            Список вебхуков
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/webhooks")
            response.raise_for_status()

            data = response.json()
            webhooks = data.get("_embedded", {}).get("webhooks", [])

            logger.info(f"Получено {len(webhooks)} вебхуков")
            return webhooks

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить вебхуки из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def create_webhook(self, destination: str, settings: List[str]) -> Dict[str, Any]:
        """
        Создает подписку на вебхук

        Args:
            destination: URL для отправки вебхуков
            settings: Список событий для подписки (например, ["add_lead", "update_lead", "delete_lead"])

        Returns:
            Данные созданного вебхука
        """
        client = self._get_client()

        payload = {
            "destination": destination,
            "settings": settings,
        }

        try:
            response = await client.post(f"{self.base_url}/webhooks", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Создан вебхук для {destination}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать вебхук в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def delete_webhook(self, webhook_id: int) -> bool:
        """
        Удаляет подписку на вебхук

        Args:
            webhook_id: ID вебхука

        Returns:
            True если вебхук успешно удален
        """
        client = self._get_client()

        try:
            response = await client.delete(f"{self.base_url}/webhooks/{webhook_id}")
            response.raise_for_status()

            logger.info(f"Удален вебхук {webhook_id}")
            return True

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось удалить вебхук {webhook_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С ВИДЖЕТАМИ (WIDGETS) ==========

    async def get_widgets(self) -> List[Dict[str, Any]]:
        """
        Получает список установленных виджетов

        Returns:
            Список виджетов
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/widgets")
            response.raise_for_status()

            data = response.json()
            widgets = data.get("_embedded", {}).get("widgets", [])

            logger.info(f"Получено {len(widgets)} виджетов")
            return widgets

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить виджеты из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА СО ЗВОНКАМИ (CALLS) ==========

    async def create_call(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Добавляет информацию о звонке

        Args:
            call_data: Данные звонка (direction, phone, duration, call_result, call_status и т.д.)

        Returns:
            Данные созданного звонка
        """
        client = self._get_client()

        payload = [call_data]

        try:
            response = await client.post(f"{self.base_url}/calls", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info("Создан звонок")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать звонок в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С ИСТОЧНИКАМИ (SOURCES) ==========

    async def get_sources(self, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает список источников

        Args:
            limit: Количество источников на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список источников
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/sources", params=params)
            response.raise_for_status()

            data = response.json()
            sources = data.get("_embedded", {}).get("sources", [])

            logger.info(f"Получено {len(sources)} источников")
            return sources

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить источники из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С РОЛЯМИ (ROLES) ==========

    async def get_roles(self, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        """
        Получает список ролей

        Args:
            limit: Количество ролей на странице (макс. 250)
            page: Номер страницы

        Returns:
            Список ролей
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        try:
            response = await client.get(f"{self.base_url}/roles", params=params)
            response.raise_for_status()

            data = response.json()
            roles = data.get("_embedded", {}).get("roles", [])

            logger.info(f"Получено {len(roles)} ролей")
            return roles

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить роли из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_role(self, role_id: int) -> Dict[str, Any]:
        """
        Получает роль по ID

        Args:
            role_id: ID роли

        Returns:
            Данные роли
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/roles/{role_id}")
            response.raise_for_status()

            logger.info(f"Получена роль {role_id}")
            return response.json()

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить роль {role_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С КОРОТКИМИ ССЫЛКАМИ (SHORT LINKS) ==========

    async def create_short_link(self, url: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Создает короткую ссылку

        Args:
            url: Исходный URL
            metadata: Метаданные для ссылки

        Returns:
            Данные созданной короткой ссылки
        """
        client = self._get_client()

        payload = {
            "url": url,
        }

        if metadata:
            payload["metadata"] = metadata

        try:
            response = await client.post(f"{self.base_url}/short_links", json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Создана короткая ссылка для {url}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось создать короткую ссылку в AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    # ========== РАБОТА С БЕСЕДАМИ (TALKS) ==========

    async def get_talks(
        self,
        limit: int = 50,
        page: int = 1,
        filter_contact_id: Optional[int] = None,
        filter_entity_id: Optional[int] = None,
        filter_entity_type: Optional[str] = None,
        filter_is_in_work: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает список бесед из AmoCRM

        Args:
            limit: Максимальное количество бесед (макс. 250)
            page: Номер страницы
            filter_contact_id: Фильтр по ID контакта
            filter_entity_id: Фильтр по ID сущности (сделка/покупатель)
            filter_entity_type: Фильтр по типу сущности ("lead", "customer")
            filter_is_in_work: Фильтр по статусу "в работе"

        Returns:
            Список бесед
        """
        client = self._get_client()

        params: Dict[str, Any] = {
            "limit": min(limit, 250),
            "page": page,
        }

        if filter_contact_id is not None:
            params["filter[contact_id]"] = filter_contact_id
        if filter_entity_id is not None:
            params["filter[entity_id]"] = filter_entity_id
        if filter_entity_type is not None:
            params["filter[entity_type]"] = filter_entity_type
        if filter_is_in_work is not None:
            params["filter[is_in_work]"] = "true" if filter_is_in_work else "false"

        try:
            response = await client.get(f"{self.base_url}/talks", params=params)
            response.raise_for_status()

            data = response.json()
            talks = data.get("_embedded", {}).get("talks", [])

            logger.info(f"Получено {len(talks)} бесед из AmoCRM (subdomain={self.subdomain})")
            return talks

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить беседы из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def get_talk_by_id(self, talk_id: int) -> Dict[str, Any]:
        """
        Получает информацию о конкретной беседе по ID

        Args:
            talk_id: ID беседы

        Returns:
            Данные беседы
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self.base_url}/talks/{talk_id}")
            response.raise_for_status()

            talk = response.json()
            logger.info(f"Получена беседа {talk_id} из AmoCRM")
            return talk

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось получить беседу {talk_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def close_talk(self, talk_id: int, force_close: bool = False) -> bool:
        """
        Закрывает беседу по ID

        Если force_close=False, может запустить NPS-бота (если он включен в настройках).
        Если force_close=True, беседа закроется принудительно без NPS.

        Args:
            talk_id: ID беседы
            force_close: Принудительное закрытие без NPS-бота

        Returns:
            True если беседа успешно закрыта
        """
        client = self._get_client()

        payload = {"force_close": force_close}

        try:
            response = await client.post(f"{self.base_url}/talks/{talk_id}/close", json=payload)
            response.raise_for_status()

            logger.info(f"Беседа {talk_id} закрыта (force_close={force_close})")
            return True

        except httpx.HTTPStatusError as e:
            # Статус 422 означает что беседа уже закрыта
            if e.response.status_code == 422:
                logger.warning(f"Беседа {talk_id} уже закрыта или находится в процессе закрытия")
                return False

            raise httpx.HTTPStatusError(
                f"Не удалось закрыть беседу {talk_id} из AmoCRM (subdomain={self.subdomain}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e


def register_subdomain(subdomain: str, access_token: str) -> None:
    """
    Регистрирует маппинг subdomain -> access_token

    Args:
        subdomain: Поддомен аккаунта AmoCRM
        access_token: Токен доступа OAuth 2.0
    """
    _subdomain_to_token[subdomain] = access_token
    logger.info(f"Зарегистрирован маппинг для subdomain: {subdomain}")


def get_amocrm_client(
    subdomain: Optional[str] = None,
    access_token: Optional[str] = None,
) -> AmoCRMClient:
    """
    Фабричная функция для создания клиента AmoCRM (singleton)

    Возвращает существующий клиент из кеша или создает новый.
    Если access_token не указан, пытается получить из маппинга по subdomain.
    Если параметры не указаны, пытается получить из settings.
    """
    # Пытаемся получить из настроек, если есть
    if hasattr(settings, 'amocrm'):
        subdomain = subdomain or settings.amocrm.subdomain
        access_token = access_token or settings.amocrm.access_token

    if not subdomain:
        raise ValueError("Необходимо указать subdomain для AmoCRM")

    # Если access_token не передан, пытаемся получить из маппинга
    if not access_token and subdomain in _subdomain_to_token:
        access_token = _subdomain_to_token[subdomain]
        logger.debug(f"Использован access_token из маппинга для subdomain: {subdomain}")

    if not access_token:
        raise ValueError(f"Не найден access_token для subdomain '{subdomain}'. Зарегистрируйте его через register_subdomain()")

    # Создаем ключ для кеша
    cache_key = (subdomain, access_token)

    # Проверяем наличие клиента в кеше
    if cache_key not in _client_cache:
        _client_cache[cache_key] = AmoCRMClient(
            subdomain=subdomain,
            access_token=access_token,
        )
        logger.info(f"Создан новый singleton клиент AmoCRM для {subdomain}")

    return _client_cache[cache_key]
