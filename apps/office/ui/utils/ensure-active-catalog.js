/**
 * Активный каталог для списка и создания документов: из стора или первый доступный / новый «Общие».
 */
import { OfficeStore } from '../store/office.store.js';

/**
 * @param {import('../services/office-api.service.js').OfficeAPIService} api
 * @param {(key: string) => string} t
 * @returns {Promise<string>}
 */
export async function ensureActiveCatalogId(api, t) {
    const existing = OfficeStore.state.catalog.activeCatalogId?.trim() || '';
    if (existing) {
        return existing;
    }
    const catRes = await api.listCatalogs();
    const items = Array.isArray(catRes.items) ? catRes.items : [];
    let catalogId;
    if (items.length === 0) {
        const created = await api.createCatalog(t('list.defaultCatalogTitle'));
        catalogId =
            typeof created.catalog_id === 'string' ? created.catalog_id.trim() : '';
        if (!catalogId) {
            throw new Error(t('list.catalogBootstrapError'));
        }
    } else {
        const first = items[0];
        catalogId =
            typeof first.catalog_id === 'string' ? first.catalog_id.trim() : '';
        if (!catalogId) {
            throw new Error(t('list.catalogBootstrapError'));
        }
    }
    OfficeStore.setActiveCatalogId(catalogId);
    return catalogId;
}
