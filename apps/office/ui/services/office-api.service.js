/**
 * REST к BFF documents (/documents/api/v1).
 */
import { BaseService } from '@platform/lib/services/BaseService.js';
import { getActivePlatformNamespaceName } from '@platform/lib/utils/platform-namespace.js';

export class OfficeAPIService extends BaseService {
    /**
     * @param {string} [baseURL]
     * @param {() => string} getCompanyId — текущая компания (из auth после validateToken).
     */
    constructor(baseURL = '/documents/api/v1', getCompanyId = () => '') {
        super(baseURL);
        this._getCompanyId = typeof getCompanyId === 'function' ? getCompanyId : () => '';
    }

    _companyId() {
        try {
            return this._getCompanyId() || '';
        } catch {
            return '';
        }
    }

    async _fetch(method, path, data, options = {}) {
        const ns = getActivePlatformNamespaceName(this._companyId());
        const headers = {
            ...(options.headers || {}),
            'X-Platform-Namespace': ns,
        };
        return super._fetch(method, path, data, { ...options, headers });
    }

    async getIntegrationStatus() {
        return this.get('/integration/status');
    }

    async listDocuments(catalogId) {
        if (typeof catalogId !== 'string' || catalogId.trim().length === 0) {
            throw new Error('catalogId is required');
        }
        return this.get('/documents', { catalog_id: catalogId.trim() });
    }

    async listNamespaces() {
        return this.get('/namespaces');
    }

    async listCompanyMembers() {
        return this.get('/company-members');
    }

    async listCatalogs() {
        return this.get('/catalogs');
    }

    /**
     * @param {string} catalogId
     */
    async getCatalog(catalogId) {
        return this.get(`/catalogs/${encodeURIComponent(catalogId)}`);
    }

    /**
     * @param {string} title
     */
    async createCatalog(title) {
        return this.post('/catalogs', { title });
    }

    /**
     * @param {string} catalogId
     * @param {string} title
     */
    async patchCatalog(catalogId, title) {
        return this.patch(`/catalogs/${encodeURIComponent(catalogId)}`, { title });
    }

    /**
     * @param {string} catalogId
     */
    async deleteCatalog(catalogId) {
        return this.delete(`/catalogs/${encodeURIComponent(catalogId)}`);
    }

    /**
     * @param {string} catalogId
     */
    async listCatalogMembers(catalogId) {
        return this.get(`/catalogs/${encodeURIComponent(catalogId)}/members`);
    }

    /**
     * @param {string} catalogId
     * @param {string} userId
     */
    async addCatalogMember(catalogId, userId) {
        return this.post(`/catalogs/${encodeURIComponent(catalogId)}/members`, {
            user_id: userId,
        });
    }

    /**
     * @param {string} catalogId
     * @param {string} userId
     */
    async removeCatalogMember(catalogId, userId) {
        return this.delete(`/catalogs/${encodeURIComponent(catalogId)}/members/${encodeURIComponent(userId)}`);
    }

    /**
     * @param {string} title
     * @param {{ document_type?: 'word'|'cell'|'slide', spreadsheet_format?: 'xlsx'|'csv' }} [opts]
     */
    async createEmptyDocument(title, opts = {}) {
        const document_type = opts.document_type ?? 'word';
        /** @type {{ title: string, document_type: string, spreadsheet_format?: string, catalog_id?: string }} */
        const body = { title, document_type };
        if (document_type === 'cell') {
            body.spreadsheet_format = opts.spreadsheet_format ?? 'xlsx';
        }
        if (typeof opts.catalog_id === 'string' && opts.catalog_id.trim().length > 0) {
            body.catalog_id = opts.catalog_id.trim();
        }
        return this.post('/documents/empty', body);
    }

    /**
     * @param {File} file
     * @param {string} [title]
     */
    async uploadDocument(file, title, catalogId) {
        const form = new FormData();
        form.append('file', file);
        if (typeof title === 'string' && title.trim().length > 0) {
            form.append('title', title.trim());
        }
        if (typeof catalogId === 'string' && catalogId.trim().length > 0) {
            form.append('catalog_id', catalogId.trim());
        }
        const url = `${this.baseUrl}/documents`;
        const ns = getActivePlatformNamespaceName(this._companyId());
        const response = await fetch(url, {
            method: 'POST',
            body: form,
            credentials: 'include',
            headers: {
                'X-Platform-Namespace': ns,
            },
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => null);
            throw new Error(this._formatError(errorData, response.status));
        }
        return response.json();
    }

    /**
     * @param {string} bindingId
     */
    async getEditorConfig(bindingId) {
        return this.get(`/documents/${encodeURIComponent(bindingId)}/editor-config`);
    }

    /**
     * @param {string} bindingId
     * @param {string} title
     */
    async renameDocument(bindingId, title) {
        return this.patch(`/documents/${encodeURIComponent(bindingId)}`, { title });
    }

    /**
     * @param {string} bindingId
     */
    async deleteDocument(bindingId) {
        return this.delete(`/documents/${encodeURIComponent(bindingId)}`);
    }
}
