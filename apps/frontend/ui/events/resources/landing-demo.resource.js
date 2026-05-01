/**
 * Публичный каталог демо-агентов лендинга (без авторизации).
 *
 * Backend:
 *   GET  /frontend/api/public/landing-agents
 *   POST /frontend/api/public/landing-agents/session
 */
import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const landingAgentsLoadOp = createAsyncOp({
    name: 'frontend/landing_agents_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/public/landing-agents' },
    request: async () => {
        return httpRequest({
            method: 'GET',
            url: '/frontend/api/public/landing-agents',
            credentials: 'same-origin',
        });
    },
});

export const landingDemoSessionOp = createAsyncOp({
    name: 'frontend/landing_demo_session',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/public/landing-agents/session' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('frontend/landing_demo_session: payload required');
        }
        const embedId = payload.embed_id;
        if (typeof embedId !== 'string' || embedId === '') {
            throw new Error('frontend/landing_demo_session: embed_id required');
        }
        const expires =
            typeof payload.expires_in_seconds === 'number' && payload.expires_in_seconds >= 60
                ? payload.expires_in_seconds
                : 300;
        return httpRequest({
            method: 'POST',
            url: '/frontend/api/public/landing-agents/session',
            credentials: 'same-origin',
            body: { embed_id: embedId, expires_in_seconds: expires },
        });
    },
});
