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
import { isPlainRecord, payloadFields } from '../payload.js';

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

function unknownItems(value: unknown, eventType: string): unknown[] {
    if (!Array.isArray(value)) {
        throw new Error(`${eventType}: payload.items must be an array`);
    }
    const items: unknown[] = [];
    for (const item of value) items.push(item);
    return items;
}

function isTeamMember(value: unknown): value is TeamMemberRecord {
    if (!isPlainRecord(value)) return false;
    const userId = value.user_id;
    return userId === undefined || typeof userId === 'string';
}

function memberRecords(value: unknown, eventType: string): TeamMemberRecord[] {
    const records: TeamMemberRecord[] = [];
    for (const item of unknownItems(value, eventType)) {
        if (!isTeamMember(item)) {
            throw new Error(`${eventType}: payload item must be a member object`);
        }
        records.push(item);
    }
    return records;
}

export function teamReducer(state: TeamState = initialTeamState, event: PlatformEvent): TeamState {
    switch (event.type) {
        case TEAM_EVENTS.MEMBERS_LOAD_REQUESTED:
            return { ...state, loading: true };
        case TEAM_EVENTS.MEMBERS_LOADED: {
            return { ...state, loading: false, members: memberRecords(payloadFields(event).items, event.type) };
        }
        case TEAM_EVENTS.MEMBERS_LOAD_FAILED:
            return { ...state, loading: false };
        case TEAM_EVENTS.SEARCH_LOADED: {
            const p = payloadFields(event);
            if (typeof p.q !== 'string' || !p.q) return state;
            return { ...state, searchByQ: { ...state.searchByQ, [p.q]: memberRecords(p.items, event.type) } };
        }
        case TEAM_EVENTS.INVITE_GENERATED: {
            const p = payloadFields(event);
            if (typeof p.role !== 'string' || !p.role || typeof p.link !== 'string' || !p.link) return state;
            return { ...state, inviteLinks: { ...state.inviteLinks, [p.role]: p.link } };
        }
        case TEAM_EVENTS.MEMBER_REMOVED: {
            const userId = (payloadFields(event)).user_id;
            if (typeof userId !== 'string' || !userId) return state;
            return { ...state, members: state.members.filter((m) => m.user_id !== userId) };
        }
        default:
            return state;
    }
}

export const teamSlice = { reducer: teamReducer, initial: initialTeamState };
