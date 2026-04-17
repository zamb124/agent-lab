/**
 * Ответ GET …/api/companies/me: на сервисе frontend — { items: CompanyBrief[] };
 * на sync/crm/rag/flows/office — core-роутер, массив CompanyBrief[].
 */
export function companiesMeItems(body) {
    if (Array.isArray(body)) {
        return body;
    }
    if (body && typeof body === 'object' && Array.isArray(body.items)) {
        return body.items;
    }
    throw new Error(
        'Некорректный ответ /api/companies/me: ожидался массив компаний или объект с полем items',
    );
}
