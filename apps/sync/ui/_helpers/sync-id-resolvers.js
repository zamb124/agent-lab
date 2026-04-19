/**
 * Helpers для разрешения id и отображаемых имён в Sync UI.
 *
 * Чистые функции без зависимостей от bus/state. Заменяют любые
 * `a || b` выборы-источника на явные `typeof`-проверки (zero-fallback canon
 * из `frontend.mdc`).
 *
 * Лежат в нейтральном слое `_helpers/`, чтобы быть доступными как из
 * `components/`, так и из `events/resources/` (фабрики), без нарушения
 * слоёв.
 */

/**
 * Идентификатор пространства: `space_id` если строка, иначе `id`.
 * Возвращает пустую строку если оба поля отсутствуют (вызывающий обязан
 * проверить пустоту перед использованием как ключа).
 */
export function resolveSpaceId(space) {
    if (!space || typeof space !== 'object') return '';
    if (typeof space.space_id === 'string' && space.space_id !== '') return space.space_id;
    if (typeof space.id === 'string' && space.id !== '') return space.id;
    return '';
}

/**
 * Отображаемое имя участника: `name` если непустая строка, иначе `user_id`.
 * Возвращает пустую строку если member null/undefined.
 */
export function resolveDisplayName(member) {
    if (!member || typeof member !== 'object') return '';
    if (typeof member.name === 'string' && member.name !== '') return member.name;
    if (typeof member.display_name === 'string' && member.display_name !== '') return member.display_name;
    if (typeof member.user_id === 'string') return member.user_id;
    return '';
}

/**
 * Заголовок канала: для `direct` — `peer.display_name | peer.user_id`,
 * иначе — `channel.name | channel.id`. Никогда не undefined.
 */
export function resolveChannelTitle(channel) {
    if (!channel || typeof channel !== 'object') return '';
    if (channel.type === 'direct' && channel.peer && typeof channel.peer === 'object') {
        if (typeof channel.peer.display_name === 'string' && channel.peer.display_name !== '') {
            return channel.peer.display_name;
        }
        if (typeof channel.peer.user_id === 'string') return channel.peer.user_id;
    }
    if (typeof channel.name === 'string' && channel.name !== '') return channel.name;
    if (typeof channel.id === 'string') return channel.id;
    return '';
}

/**
 * Безопасный non-empty preview: `value` если непустая строка, иначе fallback.
 * `fallback` обязателен; функция гарантирует что вернёт строку.
 */
export function resolveNonEmptyString(value, fallback) {
    if (typeof value === 'string' && value !== '') return value;
    if (typeof fallback !== 'string') {
        throw new Error('resolveNonEmptyString: fallback must be string');
    }
    return fallback;
}
