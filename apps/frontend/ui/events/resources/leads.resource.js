/**
 * Ресурсы leads — заявки с лендинга и системный список заявок.
 *
 * API (apps/frontend/api/leads.py):
 *   POST /api/leads             ← LeadCreateBody (name, email|phone обязательны)
 *   GET  /api/lead-requests     → { items, next_cursor, has_more } (только system)
 *
 * Состав:
 *   - leadSubmitOp:  POST /leads, success/error toasts.
 *   - leadRequestsList: cursor-list по /lead-requests, statusMap 403→forbidden.
 */

import { createAsyncOp, createCursorList } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const BASE = '/frontend/api';

export const leadSubmitOp = createAsyncOp({
    name: 'frontend/lead_submit',
    successToastKey: 'frontend:leads_page.toast_submitted',
    errorToastKey: 'frontend:leads_page.toast_submit_failed',
    restMirror: { method: 'POST', path: '/frontend/api/leads' },
    request: async ({ payload }) => await httpRequest({
        method: 'POST',
        url: `${BASE}/leads`,
        body: payload && typeof payload === 'object' ? payload : {},
    }),
});

export const leadRequestsList = createCursorList({
    name: 'frontend/lead_requests',
    baseUrl: '/frontend/api/lead-requests',
    pageSize: 50,
    buildQuery: () => ({}),
    statusMap: { 403: 'forbidden' },
    errorToastKey: 'frontend:leads_page.load_error',
});
