import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createTeamEffect } from '@platform/lib/events/effects/team.effect.js';
import { TEAM_EVENTS } from '@platform/lib/events/reducers/team.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('teamEffect: MEMBERS_LOAD_REQUESTED', () => {
    it('200 → MEMBERS_LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/team/members', { items: [{ user_id: 'u1' }] });
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(ev(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === TEAM_EVENTS.MEMBERS_LOADED).payload.items).toEqual([{ user_id: 'u1' }]);
    });

    it('500 → MEMBERS_LOAD_FAILED', async () => {
        fetchMock.respondStatus('GET', '/svc/api/team/members', 500);
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(ev(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === TEAM_EVENTS.MEMBERS_LOAD_FAILED)).toBeTruthy();
    });

    it('non-array items → MEMBERS_LOAD_FAILED (try/catch ловит throw)', async () => {
        fetchMock.respondJson('GET', '/svc/api/team/members', { items: 'nope' });
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(ev(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === TEAM_EVENTS.MEMBERS_LOAD_FAILED)).toBeTruthy();
    });
});

describe('teamEffect: SEARCH_REQUESTED', () => {
    it('пустой q → no-op', async () => {
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(ev(TEAM_EVENTS.SEARCH_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('q → SEARCH_LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/team/search?q=al', { items: [{ user_id: 'u1' }] });
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(ev(TEAM_EVENTS.SEARCH_REQUESTED, { query: 'al' }), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === TEAM_EVENTS.SEARCH_LOADED);
        expect(loaded.payload).toEqual({ q: 'al', items: [{ user_id: 'u1' }] });
    });
});

describe('teamEffect: INVITE_GENERATE_REQUESTED', () => {
    it('default role=developer', async () => {
        fetchMock.respondJson('POST', '/svc/api/invites/generate', { invite_url: 'https://join/x' });
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(ev(TEAM_EVENTS.INVITE_GENERATE_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        const generated = dispatched.find((d) => d.type === TEAM_EVENTS.INVITE_GENERATED);
        expect(generated.payload).toEqual({ role: 'developer', link: 'https://join/x' });
    });
});

describe('teamEffect: MEMBER_ROLE_UPDATE_REQUESTED', () => {
    it('требует user_id и roles массив', async () => {
        await expect(createTeamEffect({ baseUrl: '/svc' })(
            ev(TEAM_EVENTS.MEMBER_ROLE_UPDATE_REQUESTED, { user_id: 'u1' }),
            buildCtx(() => ({}), []),
        )).rejects.toThrow(/roles/);
    });

    it('успех → UPDATED + MEMBERS_LOAD_REQUESTED reload', async () => {
        fetchMock.respondJson('PATCH', '/svc/api/team/members/u1', { ok: true });
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(
            ev(TEAM_EVENTS.MEMBER_ROLE_UPDATE_REQUESTED, { user_id: 'u1', roles: ['admin'] }),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.find((d) => d.type === TEAM_EVENTS.MEMBER_ROLE_UPDATED)).toBeTruthy();
        expect(dispatched.find((d) => d.type === TEAM_EVENTS.MEMBERS_LOAD_REQUESTED)).toBeTruthy();
    });
});

describe('teamEffect: MEMBER_REMOVE_REQUESTED', () => {
    it('требует user_id', async () => {
        await expect(createTeamEffect({ baseUrl: '/svc' })(
            ev(TEAM_EVENTS.MEMBER_REMOVE_REQUESTED, {}),
            buildCtx(() => ({}), []),
        )).rejects.toThrow(/user_id/);
    });

    it('204 → MEMBER_REMOVED', async () => {
        fetchMock.respondStatus('DELETE', '/svc/api/team/members/u1', 204);
        const dispatched = [];
        await createTeamEffect({ baseUrl: '/svc' })(
            ev(TEAM_EVENTS.MEMBER_REMOVE_REQUESTED, { user_id: 'u1' }),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.find((d) => d.type === TEAM_EVENTS.MEMBER_REMOVED).payload.user_id).toBe('u1');
    });
});
