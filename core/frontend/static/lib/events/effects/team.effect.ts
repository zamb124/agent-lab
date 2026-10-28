/**
 * Эффект team — участники, поиск, инвайт-ссылки, роли.
 */

import { httpRequest } from '../http.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { TEAM_EVENTS } from '../reducers/team.js';
import { isPlainRecord, payloadFields, stringField } from '../payload.js';

function errorMessage(err: unknown): string {
    if (err instanceof Error && err.message.length > 0) return err.message;
    if (isPlainRecord(err) && typeof err.message === 'string' && err.message.length > 0) return err.message;
    throw new Error('team.members: failure has no message');
}

function itemsOf(data: unknown, label: string): unknown[] {
    if (!isPlainRecord(data) || !Array.isArray(data.items)) {
        throw new Error(`${label}: items must be array`);
    }
    const items: unknown[] = [];
    for (const item of data.items) items.push(item);
    return items;
}

function inviteLink(data: unknown): string {
    if (!isPlainRecord(data)) {
        throw new Error('team.invite: response must be an object');
    }
    const url = data.invite_url;
    if (typeof url === 'string' && url.length > 0) return url;
    const link = data.link;
    if (typeof link === 'string' && link.length > 0) return link;
    throw new Error('team.invite: invite_url or link required');
}

export function createTeamEffect({ baseUrl }: { baseUrl?: string }): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    const base = typeof baseUrl === 'string' ? baseUrl : '';
    return async function teamEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case TEAM_EVENTS.MEMBERS_LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/api/team/members` });
                    ctx.dispatch(TEAM_EVENTS.MEMBERS_LOADED, { items: itemsOf(data, 'team.members') }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(TEAM_EVENTS.MEMBERS_LOAD_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case TEAM_EVENTS.SEARCH_REQUESTED: {
                const q = stringField(payloadFields(event).query);
                if (q === null) return;
                const data = await httpRequest({ method: 'GET', url: `${base}/api/team/search`, query: { q } });
                ctx.dispatch(TEAM_EVENTS.SEARCH_LOADED, { q, items: itemsOf(data, 'team.search') }, { causation_id: event.id, source: 'http' });
                return;
            }
            case TEAM_EVENTS.INVITE_GENERATE_REQUESTED: {
                const rawRole = stringField(payloadFields(event).role);
                const role = rawRole === null ? 'developer' : rawRole;
                const data = await httpRequest({ method: 'POST', url: `${base}/api/invites/generate`, body: { role } });
                ctx.dispatch(TEAM_EVENTS.INVITE_GENERATED, { role, link: inviteLink(data) }, { causation_id: event.id, source: 'http' });
                return;
            }
            case TEAM_EVENTS.MEMBER_ROLE_UPDATE_REQUESTED: {
                const fields = payloadFields(event);
                const userId = stringField(fields.user_id);
                const roles = fields.roles;
                if (userId === null || !Array.isArray(roles)) throw new Error('team.effect: user_id and roles required');
                await httpRequest({ method: 'PATCH', url: `${base}/api/team/members/${encodeURIComponent(userId)}`, body: { roles } });
                ctx.dispatch(TEAM_EVENTS.MEMBER_ROLE_UPDATED, { user_id: userId, roles }, { causation_id: event.id, source: 'http' });
                ctx.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null, { causation_id: event.id });
                return;
            }
            case TEAM_EVENTS.MEMBER_REMOVE_REQUESTED: {
                const userId = stringField(payloadFields(event).user_id);
                if (userId === null) throw new Error('team.effect: user_id required');
                await httpRequest({ method: 'DELETE', url: `${base}/api/team/members/${encodeURIComponent(userId)}` });
                ctx.dispatch(TEAM_EVENTS.MEMBER_REMOVED, { user_id: userId }, { causation_id: event.id, source: 'http' });
                return;
            }
            default:
                return;
        }
    };
}
