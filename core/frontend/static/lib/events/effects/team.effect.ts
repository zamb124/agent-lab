/**
 * Эффект team — участники, поиск, инвайт-ссылки, роли.
 */

import { httpRequest } from '../http.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { TEAM_EVENTS } from '../reducers/team.js';

export function createTeamEffect({ baseUrl }: { baseUrl?: string }): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    const base = baseUrl || '';
    return async function teamEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case TEAM_EVENTS.MEMBERS_LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/api/team/members` }) as { items?: unknown } | null;
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('team.members: items must be array');
                    }
                    ctx.dispatch(TEAM_EVENTS.MEMBERS_LOADED, { items: data.items }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(TEAM_EVENTS.MEMBERS_LOAD_FAILED, { message: String(err && (err as Error).message ? (err as Error).message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case TEAM_EVENTS.SEARCH_REQUESTED: {
                const q = ((event.payload ?? {}) as { query?: unknown }).query;
                if (typeof q !== 'string' || !q) return;
                const data = await httpRequest({ method: 'GET', url: `${base}/api/team/search`, query: { q } }) as { items?: unknown } | null;
                if (!data || !Array.isArray(data.items)) {
                    throw new Error('team.search: items must be array');
                }
                ctx.dispatch(TEAM_EVENTS.SEARCH_LOADED, { q, items: data.items }, { causation_id: event.id, source: 'http' });
                return;
            }
            case TEAM_EVENTS.INVITE_GENERATE_REQUESTED: {
                const rawRole = ((event.payload ?? {}) as { role?: unknown }).role;
                const role = typeof rawRole === 'string' && rawRole ? rawRole : 'developer';
                const data = await httpRequest({ method: 'POST', url: `${base}/api/invites/generate`, body: { role } }) as { invite_url?: string; link?: string };
                ctx.dispatch(TEAM_EVENTS.INVITE_GENERATED, { role, link: data.invite_url || data.link }, { causation_id: event.id, source: 'http' });
                return;
            }
            case TEAM_EVENTS.MEMBER_ROLE_UPDATE_REQUESTED: {
                const { user_id: userId, roles } = (event.payload ?? {}) as { user_id?: unknown; roles?: unknown };
                if (typeof userId !== 'string' || !userId || !Array.isArray(roles)) throw new Error('team.effect: user_id and roles required');
                await httpRequest({ method: 'PATCH', url: `${base}/api/team/members/${encodeURIComponent(userId)}`, body: { roles } });
                ctx.dispatch(TEAM_EVENTS.MEMBER_ROLE_UPDATED, { user_id: userId, roles }, { causation_id: event.id, source: 'http' });
                ctx.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null, { causation_id: event.id });
                return;
            }
            case TEAM_EVENTS.MEMBER_REMOVE_REQUESTED: {
                const userId = ((event.payload ?? {}) as { user_id?: unknown }).user_id;
                if (typeof userId !== 'string' || !userId) throw new Error('team.effect: user_id required');
                await httpRequest({ method: 'DELETE', url: `${base}/api/team/members/${encodeURIComponent(userId)}` });
                ctx.dispatch(TEAM_EVENTS.MEMBER_REMOVED, { user_id: userId }, { causation_id: event.id, source: 'http' });
                return;
            }
            default:
                return;
        }
    };
}
