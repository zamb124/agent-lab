import {
    PLACEHOLDER_MEETING_COLLECTION,
    PLACEHOLDER_NON_PERSON_COLLECTION,
} from '@platform/lib/utils/placeholder-avatar.js';

/**
 * Коллекция alohe для плейсхолдера аватара канала (не direct).
 * @param {{ type?: string }} channel
 * @returns {string}
 */
export function syncChannelPlaceholderCollection(channel) {
    if (!channel || typeof channel !== 'object') {
        throw new Error('syncChannelPlaceholderCollection: channel required');
    }
    const t = channel.type;
    if (t === 'calendar_meeting') return PLACEHOLDER_MEETING_COLLECTION;
    if (typeof t !== 'string' || t === '') {
        throw new Error('syncChannelPlaceholderCollection: channel.type required');
    }
    return PLACEHOLDER_NON_PERSON_COLLECTION;
}
