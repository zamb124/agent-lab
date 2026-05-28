/**
 * Слайс team.
 *
 * state.team:
 *   members:     Array
 *   loading:     boolean
 *   searchByQ:   { [q]: Array }
 *   inviteLinks: { [role]: string }
 */

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

export const initialTeamState = Object.freeze({
    members: [],
    loading: false,
    searchByQ: {},
    inviteLinks: {},
});

export function teamReducer(state = initialTeamState, event) {
    switch (event.type) {
        case TEAM_EVENTS.MEMBERS_LOAD_REQUESTED:
            return { ...state, loading: true };
        case TEAM_EVENTS.MEMBERS_LOADED: {
            if (!event.payload || !Array.isArray(event.payload.items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, loading: false, members: event.payload.items };
        }
        case TEAM_EVENTS.MEMBERS_LOAD_FAILED:
            return { ...state, loading: false };
        case TEAM_EVENTS.SEARCH_LOADED: {
            const { q, items } = event.payload || {};
            if (!q) return state;
            if (!Array.isArray(items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, searchByQ: { ...state.searchByQ, [q]: items } };
        }
        case TEAM_EVENTS.INVITE_GENERATED: {
            const { role, link } = event.payload || {};
            if (!role || !link) return state;
            return { ...state, inviteLinks: { ...state.inviteLinks, [role]: link } };
        }
        case TEAM_EVENTS.MEMBER_REMOVED: {
            const userId = event.payload && event.payload.user_id;
            if (!userId) return state;
            return { ...state, members: state.members.filter((m) => m.user_id !== userId) };
        }
        default:
            return state;
    }
}

export const teamSlice = { reducer: teamReducer, initial: initialTeamState };
