import { describe, it, expect } from 'vitest';
import { teamReducer, initialTeamState, TEAM_EVENTS, teamSlice } from '@platform/lib/events/reducers/team.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('teamReducer', () => {
    it('initial', () => {
        expect(initialTeamState.members).toEqual([]);
        expect(teamSlice.initial).toBe(initialTeamState);
    });

    it('MEMBERS_LOAD_REQUESTED → loading=true', () => {
        const next = teamReducer(initialTeamState, ev(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED));
        expect(next.loading).toBe(true);
    });

    it('MEMBERS_LOADED без массива — throw', () => {
        expect(() => teamReducer(initialTeamState, ev(TEAM_EVENTS.MEMBERS_LOADED, {}))).toThrow(/items/);
    });

    it('MEMBERS_LOADED заполняет members', () => {
        const next = teamReducer(initialTeamState, ev(TEAM_EVENTS.MEMBERS_LOADED, { items: [{ user_id: 'u1' }] }));
        expect(next.members).toEqual([{ user_id: 'u1' }]);
        expect(next.loading).toBe(false);
    });

    it('SEARCH_LOADED кеширует по q', () => {
        const next = teamReducer(initialTeamState, ev(TEAM_EVENTS.SEARCH_LOADED, { q: 'al', items: [{ user_id: 'u1' }] }));
        expect(next.searchByQ.al).toEqual([{ user_id: 'u1' }]);
    });

    it('SEARCH_LOADED без массива — throw', () => {
        expect(() => teamReducer(initialTeamState, ev(TEAM_EVENTS.SEARCH_LOADED, { q: 'a', items: 'nope' }))).toThrow(/items/);
    });

    it('INVITE_GENERATED кладёт ссылку по роли', () => {
        const next = teamReducer(initialTeamState, ev(TEAM_EVENTS.INVITE_GENERATED, { role: 'developer', link: 'https://join/x' }));
        expect(next.inviteLinks.developer).toBe('https://join/x');
    });

    it('MEMBER_REMOVED убирает по user_id', () => {
        const seeded = teamReducer(initialTeamState, ev(TEAM_EVENTS.MEMBERS_LOADED, { items: [{ user_id: 'u1' }, { user_id: 'u2' }] }));
        const next = teamReducer(seeded, ev(TEAM_EVENTS.MEMBER_REMOVED, { user_id: 'u1' }));
        expect(next.members).toEqual([{ user_id: 'u2' }]);
    });
});
