/**
 * Office Company Members — список участников активной компании в namespace.
 *
 * Backend (`/documents/api/v1/company-members`):
 *   GET / → JSON array[{ user_id, name, email, roles, joined_at, avatar_url }]
 *
 * Бэкенд возвращает голый массив (без OffsetPage-обёртки), поэтому фабрика
 * не пытается распаковать `result.items`. Контроллер читает прямо
 * `useOp('office/company_members').lastResult` (массив или `null`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

export const companyMembersOp = createAsyncOp({
    name: 'office/company_members',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/company-members' },
    request: ({ ctx }) => httpRequest({
        method: 'GET',
        url: '/documents/api/v1/company-members',
        headers: nsHeader(ctx),
    }),
});
