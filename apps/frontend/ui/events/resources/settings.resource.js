/**
 * Settings resources — настройки компании.
 *
 * API (apps/frontend/api/settings.py):
 *   GET   /api/settings/company  → company info + rag_embedding (provider/model + override flag)
 *   PATCH /api/settings/company  ← CompanySettingsUpdate
 *
 * Состав:
 *   - settingsLoadOp:   silent, GET /company.
 *   - settingsUpdateOp: PATCH /company; success → toast и перезапуск settingsLoadOp.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const BASE = '/frontend/api/settings';

export const settingsLoadOp = createAsyncOp({
    name: 'frontend/settings_load',
    silent: true,
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE}/company`,
    }),
});

export const settingsUpdateOp = createAsyncOp({
    name: 'frontend/settings_update',
    successToastKey: 'frontend:settings_page.toast_saved',
    errorToastKey: 'frontend:settings_page.err_save_failed',
    request: async ({ payload }) => await httpRequest({
        method: 'PATCH',
        url: `${BASE}/company`,
        body: payload || {},
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(settingsLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});
