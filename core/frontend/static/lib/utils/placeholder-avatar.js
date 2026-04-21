/**
 * Детерминированные placeholder-аватары (PNG с CDN alohe/avatars через jsDelivr).
 *
 * Юридические условия репозитория ассетов нужно проверить отдельно перед продакшеном.
 */

/** Базовый URL каталога `png/` в репозитории alohe/avatars. */
export const PLACEHOLDER_AVATAR_CDN_BASE = 'https://cdn.jsdelivr.net/gh/alohe/avatars/png/';

function buildPngNames(prefix, count) {
    return Array.from({ length: count }, (_, i) => `${prefix}_${i + 1}.png`);
}

/** Имена файлов по коллекциям (репозиторий alohe/avatars, каталог `png/`). */
export const PLACEHOLDER_AVATAR_COLLECTIONS = Object.freeze({
    memo: Object.freeze(buildPngNames('memo', 35)),
    notion: Object.freeze(buildPngNames('notion', 15)),
    vibrent: Object.freeze(buildPngNames('vibrent', 27)),
    /** Условные «персонажи» / не фото-люди (мульт, упрощённый стиль). */
    toon: Object.freeze(buildPngNames('toon', 10)),
    /** Абстрактные / 3D-объекты, мало файлов. */
    '3d': Object.freeze(buildPngNames('3d', 5)),
    bluey: Object.freeze(buildPngNames('bluey', 10)),
    teams: Object.freeze(buildPngNames('teams', 9)),
    upstream: Object.freeze(buildPngNames('upstream', 22)),
});

export const DEFAULT_PLACEHOLDER_AVATAR_COLLECTION = 'memo';

/**
 * Плейсхолдер для сущностей вне «личного профиля» (каналы, группы и т.д.):
 * не коллекция memo с мемодзи-людьми.
 */
export const PLACEHOLDER_NON_PERSON_COLLECTION = 'toon';

/** Каналы календарных встреч — более абстрактные ассеты, без «людей». */
export const PLACEHOLDER_MEETING_COLLECTION = 'upstream';

/**
 * Стабильный индекс 0..modulo-1 (тот же множитель 31, что hue в sync-hue).
 * @param {string} seed
 * @param {number} modulo
 */
export function placeholderAvatarIndexFromSeed(seed, modulo) {
    if (modulo <= 0) {
        throw new Error('placeholderAvatarIndexFromSeed: modulo must be positive');
    }
    let h = 0;
    for (let i = 0; i < seed.length; i += 1) {
        h = (h * 31 + seed.charCodeAt(i)) >>> 0;
    }
    return h % modulo;
}

/**
 * @param {string} seed — непустая строка (user_id, channel id и т.д.)
 * @param {{ collection?: string }} [options]
 * @returns {string} полный URL PNG
 */
export function getPlaceholderAvatarUrl(seed, options = {}) {
    if (typeof seed !== 'string' || seed === '') {
        throw new Error('getPlaceholderAvatarUrl: seed must be a non-empty string');
    }
    const collection = options.collection !== undefined && options.collection !== ''
        ? options.collection
        : DEFAULT_PLACEHOLDER_AVATAR_COLLECTION;
    const files = PLACEHOLDER_AVATAR_COLLECTIONS[collection];
    if (!files) {
        throw new Error(`getPlaceholderAvatarUrl: unknown collection "${collection}"`);
    }
    const index = placeholderAvatarIndexFromSeed(seed, files.length);
    return `${PLACEHOLDER_AVATAR_CDN_BASE}${files[index]}`;
}

/**
 * @param {{ avatarUrl?: string | null, seed: string, collection?: string }} args
 * @returns {{ kind: 'remote' | 'placeholder', src: string }}
 */
export function resolveAvatarImageSrc(args) {
    if (!args || typeof args !== 'object') {
        throw new Error('resolveAvatarImageSrc: args object required');
    }
    const { seed, collection } = args;
    const rawUrl = args.avatarUrl;
    const trimmed = typeof rawUrl === 'string' ? rawUrl.trim() : '';
    if (trimmed !== '') {
        return { kind: 'remote', src: trimmed };
    }
    if (typeof seed !== 'string' || seed === '') {
        throw new Error('resolveAvatarImageSrc: seed must be a non-empty string when avatarUrl is absent');
    }
    return {
        kind: 'placeholder',
        src: getPlaceholderAvatarUrl(seed, { collection }),
    };
}
