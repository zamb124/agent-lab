/**
 * Ресурсы leads — заявки с лендинга и системный список заявок.
 *
 * Состав:
 *   - leadSubmitOp: анонимная форма лендинга `POST /frontend/api/leads` — HTTP до сессии,
 *     не команда (`COMMAND_WS_HTTP_ALLOWLIST`).
 *   - leadRequestsList: cursor-list по команде `frontend/lead_requests/list_requested`
 *     (REST-зеркало `GET /frontend/api/lead-requests`, только system), statusMap 403→forbidden.
 */

import { createAsyncOp, createCursorList } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const leadSubmitOp = createAsyncOp({
    name: 'frontend/lead_submit',
    successToastKey: 'frontend:leads_page.toast_submitted',
    errorToastKey: 'frontend:leads_page.toast_submit_failed',
    restMirror: { method: 'POST', path: '/frontend/api/leads' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('frontend/lead_submit payload object required');
        }
        return await httpRequest({
            method: 'POST',
            url: '/frontend/api/leads',
            body: payload,
        });
    },
});

export const leadRequestsList = createCursorList({
    name: 'frontend/lead_requests',
    baseUrl: '/frontend/api/lead-requests',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'frontend/lead_requests/list_requested',
    pageSize: 50,
    buildQuery: () => ({}),
    statusMap: { 403: 'forbidden' },
    errorToastKey: 'frontend:leads_page.load_error',
});
