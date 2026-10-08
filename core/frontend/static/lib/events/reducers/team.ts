/**
 * Слайс team.
 *
 * state.team:
 *   members:     Array
 *   loading:     boolean
 *   searchByQ:   { [q]: Array }
 *   inviteLinks: { [role]: string }
 */

import type { PlatformEvent } from '../contract.js';

export interface TeamMemberRecord extends Record<string, unknown> {
    user_id?: string;
}

export interface TeamState {
    members: TeamMemberRecord[];
    loading: boolean;
    searchByQ: Record<string, TeamMemberRecord[]>;
    inviteLinks: Record<string, string>;
}

export const TEAM_EVENTS = Object.freeze({
    MEMBERS_LOAD_REQUESTED: 'team/members/load_requested',
    MEMBERS_LOADED:         'team/members/loaded',
    MEMBERS_LOAD_FAILED:    'team/members/load_failed',
    SEARCH_REQUESTED:       'team/search/run_requested',
    SEARCH_LOADED:          'team/search/loaded',
    INVITE_GENERATE_REQUESTED:'team/invite/generate_requested',
    INVITE_GENERATED:       'team/invite/generated',
    MEMBER_ROLE_UPDATE_REQUESTED:'team/member_role/update_requested',
    MEMBER_ROLE_UPDATED:    'team/member_role/updated',
    MEMBER_REMOVE_REQUESTED:'team/member/remove_requested',
    MEMBER_REMOVED:         'team/member/removed',
});

export const initialTeamState: TeamState = Object.freeze({
    members: [],
    loading: false,
    searchByQ: {},
    inviteLinks: {},
});

export function teamReducer(state: TeamState = initialTeamState, event: PlatformEvent): TeamState {
    switch (event.type) {
        case TEAM_EVENTS.MEMBERS_LOAD_REQUESTED:
            return { ...state, loading: true };
        case TEAM_EVENTS.MEMBERS_LOADED: {
            const items = ((event.payload || {}) as { items?: unknown }).items;
            if (!Array.isArray(items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, loading: false, members: items as TeamMemberRecord[] };
        }
        case TEAM_EVENTS.MEMBERS_LOAD_FAILED:
            return { ...state, loading: false };
        case TEAM_EVENTS.SEARCH_LOADED: {
            const p = (event.payload || {}) as { q?: unknown; items?: unknown };
            if (typeof p.q !== 'string' || !p.q) return state;
            if (!Array.isArray(p.items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, searchByQ: { ...state.searchByQ, [p.q]: p.items as TeamMemberRecord[] } };
        }
        case TEAM_EVENTS.INVITE_GENERATED: {
            const p = (event.payload || {}) as { role?: unknown; link?: unknown };
            if (typeof p.role !== 'string' || !p.role || typeof p.link !== 'string' || !p.link) return state;
            return { ...state, inviteLinks: { ...state.inviteLinks, [p.role]: p.link } };
        }
        case TEAM_EVENTS.MEMBER_REMOVED: {
            const userId = ((event.payload || {}) as { user_id?: unknown }).user_id;
            if (typeof userId !== 'string' || !userId) return state;
            return { ...state, members: state.members.filter((m) => m.user_id !== userId) };
        }
        default:
            return state;
    }
}

export const teamSlice = { reducer: teamReducer, initial: initialTeamState };
