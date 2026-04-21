/**
 * Helpers для отображения каналов и пользователей в sync UI.
 * Чистые функции без зависимостей от bus/state.
 *
 * Все выборы-источника — через явные `typeof`-проверки, не `||`-фолбеки
 * (см. `frontend.mdc` — zero-fallback canon).
 */

import { resolveChannelTitle, resolveDisplayName } from '../../_helpers/sync-id-resolvers.js';
import { getTypingIndicatorLine } from '../../_helpers/sync-typing.js';

/**
 * Заголовок канала. Тонкая обёртка над `resolveChannelTitle` для
 * совместимости со старым именем.
 */
export function channelDisplayTitle(channel) {
    return resolveChannelTitle(channel);
}

/**
 * Метка справа от канала в sidebar (namespace / Личный / Встреча).
 */
export function channelRowMetaLabel(channel, t) {
    if (!channel) return '';
    if (channel.type === 'direct') return t('sidebar.meta_direct');
    if (channel.type === 'calendar_meeting') return t('sidebar.meta_meeting');
    if (typeof channel.namespace === 'string' && channel.namespace !== '') {
        return channel.namespace;
    }
    return t('sidebar.meta_group');
}

/**
 * Нормализация channel_id для сравнения (убрать query-часть).
 */
export function normalizeSyncChannelId(channelId) {
    if (typeof channelId !== 'string') return '';
    return channelId.split('?')[0];
}

/**
 * Подзаголовок шапки чата: typing-индикатор / presence DM-собеседника /
 * количество участников / last-message preview.
 *
 * Typing в slice — только user_id + ts (без display_name); имена как в сайдбаре —
 * через getTypingIndicatorLine и members.
 */
export function buildChatSubtitle({
    channel,
    typingByChannel,
    presenceByUserId,
    t,
    myUserId,
    members,
}) {
    if (!channel) return '';
    const typingLine = getTypingIndicatorLine({
        typingByChannel,
        channelId: channel.id,
        threadId: null,
        myUserId: typeof myUserId === 'string' ? myUserId : '',
        members: Array.isArray(members) ? members : [],
        t,
    });
    if (typingLine !== '') return typingLine;
    if (channel.type === 'direct' && channel.peer && typeof channel.peer === 'object') {
        const presence = presenceByUserId && presenceByUserId[channel.peer.user_id];
        if (presence) {
            if (presence.online === true) return t('chat_header.subtitle_online');
            if (typeof presence.last_seen_at === 'string' && presence.last_seen_at !== '') {
                return t('chat_header.subtitle_last_seen', { at: presence.last_seen_at });
            }
        }
        return t('chat_header.subtitle_direct');
    }
    if (typeof channel.last_message_preview === 'string' && channel.last_message_preview !== '') {
        return channel.last_message_preview;
    }
    return '';
}

export { resolveChannelTitle, resolveDisplayName };
