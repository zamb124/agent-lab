/**
 * Гостевой отправитель Sync: identity `guest:{hex8}:{name}`.
 * Зеркало `apps/sync/sender_display.py::guest_display_name_from_sender_id`.
 */

const GUEST_PREFIX = 'guest:';

export function isGuestSenderId(userId) {
    if (typeof userId !== 'string') {
        throw new Error('isGuestSenderId: userId must be a string');
    }
    return userId.startsWith(GUEST_PREFIX);
}

/**
 * Имя из третьего сегмента identity. Нет имени — `null` (UI ставит i18n «Гость»).
 * Не гость — `null`.
 */
export function guestDisplayNameFromSenderId(userId) {
    if (typeof userId !== 'string') {
        throw new Error('guestDisplayNameFromSenderId: userId must be a string');
    }
    if (!userId.startsWith(GUEST_PREFIX)) {
        return null;
    }
    const parts = userId.split(':');
    if (parts.length < 3) {
        return null;
    }
    const name = parts.slice(2).join(':').trim();
    if (name === '') {
        return null;
    }
    return name;
}
