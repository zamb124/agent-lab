/**
 * Helpers для отображения каналов и пользователей в sync UI.
 * Чистые функции без зависимостей от bus/state.
 *
 * Все выборы-источника — через явные `typeof`-проверки, не `||`-фолбеки
 * (см. `frontend.mdc` — zero-fallback canon).
 */

import { resolveChannelTitle, resolveDisplayName, resolveSpaceId } from '../../_helpers/sync-id-resolvers.js';

/**
 * Заголовок канала. Тонкая обёртка над `resolveChannelTitle` для
 * совместимости со старым именем.
 */
export function channelDisplayTitle(channel) {
    return resolveChannelTitle(channel);
}

/**
 * Метка справа от канала в sidebar (имя пространства / Личный / Встреча).
 */
export function channelRowMetaLabel(channel, spacesById, t) {
    if (!channel) return '';
    if (channel.type === 'direct') return t('sidebar.meta_direct');
    if (channel.type === 'calendar_meeting') return t('sidebar.meta_meeting');
    if (typeof channel.space_id === 'string' && channel.space_id !== '') {
        const space = spacesById && spacesById[channel.space_id];
        if (space && typeof space.name === 'string' && space.name !== '') {
            return space.name;
        }
    }
    if (typeof channel.space_id !== 'string' || channel.space_id === '') {
        return t('sidebar.meta_group');
    }
    return '';
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
 */
export function buildChatSubtitle({ channel, typingByChannel, presenceByUserId, t }) {
    if (!channel) return '';
    const typingPeers = typingByChannel && typingByChannel[channel.id];
    if (typingPeers) {
        const names = [];
        for (const entry of Object.values(typingPeers)) {
            if (entry && entry.user && typeof entry.user.display_name === 'string' && entry.user.display_name !== '') {
                names.push(entry.user.display_name);
            }
        }
        if (names.length > 0) {
            return t('chat_header.subtitle_typing', { names: names.join(', ') });
        }
    }
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

export { resolveChannelTitle, resolveDisplayName, resolveSpaceId };
