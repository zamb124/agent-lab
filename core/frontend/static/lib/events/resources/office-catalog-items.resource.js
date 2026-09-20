/**
 * Содержимое office-каталога: дочерние каталоги + документы.
 * REST GET /documents/api/v1/catalogs/:catalog_id/items и
 * WS office/catalogs/items_requested — один op_catalogs_items.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const catalogItemsOp = createAsyncOp({
    name: 'office/catalog_items',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/items_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs/:catalog_id/items' },
});
