import { BaseService } from '../lib/services/BaseService.js';

/**
 * FileTypesService -- единый реестр типов файлов платформы.
 *
 * Данные загружаются один раз из GET /api/platform/file-types (Python source of truth)
 * и кешируются в памяти. Все UI-компоненты используют этот сервис вместо хардкода
 * расширений, MIME-типов и accept-строк.
 */
export class FileTypesService extends BaseService {
    constructor(baseUrl) {
        super(baseUrl);
        this._registry = [];
        this._categories = [];
        this._loaded = false;
    }

    async init() {
        const resp = await fetch('/api/platform/file-types', { credentials: 'include' });
        if (!resp.ok) {
            throw new Error(`FileTypesService: HTTP ${resp.status}`);
        }
        const data = await resp.json();
        this._categories = data.categories;
        this._registry = data.registry;
        this._loaded = true;
    }

    _assertLoaded() {
        if (!this._loaded) {
            throw new Error('FileTypesService not initialized. Call init() first.');
        }
    }

    get categories() {
        this._assertLoaded();
        return this._categories;
    }

    extensionsFor(...categories) {
        this._assertLoaded();
        const cats = new Set(categories);
        return this._registry
            .filter(e => cats.has(e.category))
            .map(e => e.extension);
    }

    mimesFor(...categories) {
        this._assertLoaded();
        const cats = new Set(categories);
        const result = new Set();
        for (const entry of this._registry) {
            if (cats.has(entry.category)) {
                for (const m of entry.mime_types) {
                    result.add(m);
                }
            }
        }
        return [...result];
    }

    acceptStringFor(...categories) {
        this._assertLoaded();
        const cats = new Set(categories);
        const exts = this.extensionsFor(...categories).sort();
        const wildcards = [];
        if (cats.has('image')) wildcards.push('image/*');
        if (cats.has('audio')) wildcards.push('audio/*');
        if (cats.has('video')) wildcards.push('video/*');
        return [...wildcards, ...exts].join(',');
    }

    isAllowedFile(file, ...categories) {
        this._assertLoaded();
        const allowedMimes = new Set(this.mimesFor(...categories));
        const allowedExts = new Set(
            this.extensionsFor(...categories).map(e => e.replace(/^\./, '')),
        );

        if (allowedMimes.has(file.type)) return true;
        if (file.type === 'application/octet-stream') {
            const ext = file.name.includes('.')
                ? file.name.slice(file.name.lastIndexOf('.') + 1).toLowerCase()
                : '';
            return allowedExts.has(ext);
        }
        const ext = file.name.includes('.')
            ? file.name.slice(file.name.lastIndexOf('.') + 1).toLowerCase()
            : '';
        return allowedExts.has(ext);
    }
}
