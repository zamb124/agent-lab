/**
 * OnlyOffice Integration Status — readonly статус наличия конфигурации DS,
 * JWT secret, callback URL.
 *
 * Бэкенд: `GET /documents/api/v1/integration/status` →
 * `OfficeIntegrationStatusResponse { configured, document_server_public_url,
 * jwt_secret_present, callback_public_base_url, ... }`.
 *
 * Используется баннером `<office-integration-banner>` для показа подсказки
 * «integration not configured» и в режиме editor для предупреждения, что
 * сервер документов не настроен.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

export const integrationStatusOp = createAsyncOp({
    name: 'office/integration_status',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/integration/status' },
    request: ({ ctx }) => httpRequest({
        method: 'GET',
        url: '/documents/api/v1/integration/status',
        headers: nsHeader(ctx),
    }),
});
