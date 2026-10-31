/**
 * Группировка registry items tool picker по tags (тул может быть в нескольких группах).
 */

/**
 * @param {unknown} item
 * @returns {string[]}
 */
export function tagsFromRegistryItem(item: any) {
    if (item && typeof item === 'object' && Array.isArray(item.tags)) {
        return item.tags.filter((x: any) => typeof x === 'string' && x.length > 0);
    }
    return [];
}

/**
 * @param {unknown[]} items
 * @param {{ search?: string, descriptionsByTag?: Map<string, { description_ru?: string, description_en?: string }> | Record<string, { description_ru?: string, description_en?: string }>, locale?: string }} [opts]
 * @returns {Array<{ tag: string, description: string, tools: unknown[] }>}
 */
export function buildToolTagGroups(items: Record<string, unknown>[], opts: Record<string, unknown> = {}) {
    const search = typeof opts.search === 'string' ? opts.search.trim().toLowerCase() : '';
    const locale = typeof opts.locale === 'string' && opts.locale.length > 0 ? opts.locale : 'ru';
    const descMap = opts.descriptionsByTag instanceof Map
        ? opts.descriptionsByTag
        : new Map(Object.entries(opts.descriptionsByTag === undefined || opts.descriptionsByTag === null ? {} : opts.descriptionsByTag));

    /** @type {Map<string, unknown[]>} */
    const byTag = new Map();
    for (const item of items) {
        if (!item || typeof item !== 'object') {
            continue;
        }
        if (search.length > 0 && !_itemMatchesSearch(item, search)) {
            continue;
        }
        const tags = tagsFromRegistryItem(item);
        const effectiveTags = tags.length > 0 ? tags : ['misc'];
        for (const tag of effectiveTags) {
            const bucket = byTag.get(tag);
            if (bucket) {
                bucket.push(item);
            } else {
                byTag.set(tag, [item]);
            }
        }
    }

    const groups = [];
    for (const tag of [...byTag.keys()].sort((a, b) => a.localeCompare(b))) {
        const storedTools = byTag.get(tag);
        const tools = storedTools === undefined ? [] : storedTools;
        tools.sort((left: any, right: any) => {
            const lt = _itemTitle(left);
            const rt = _itemTitle(right);
            return lt.localeCompare(rt, undefined, { sensitivity: 'base' });
        });
        const meta = descMap.get(tag);
        let description = '';
        if (meta && typeof meta === 'object') {
            if (locale.startsWith('en') && typeof meta.description_en === 'string') {
                description = meta.description_en;
            } else if (typeof meta.description_ru === 'string') {
                description = meta.description_ru;
            } else if (typeof meta.description_en === 'string') {
                description = meta.description_en;
            }
        }
        groups.push({ tag, description, tools });
    }
    return groups;
}

/**
 * @param {unknown} item
 * @param {string} q
 */
function _itemMatchesSearch(item: any, q: any) {
    const title = _itemTitle(item).toLowerCase();
    const id = typeof item.tool_id === 'string' ? item.tool_id.toLowerCase() : '';
    const desc = typeof item.description === 'string' ? item.description.toLowerCase() : '';
    const tags = tagsFromRegistryItem(item).join(' ').toLowerCase();
    return title.includes(q) || id.includes(q) || desc.includes(q) || tags.includes(q);
}

/**
 * @param {unknown} item
 */
function _itemTitle(item: any) {
    if (!item || typeof item !== 'object') {
        return '';
    }
    if (typeof item.title === 'string' && item.title.length > 0) {
        return item.title;
    }
    if (typeof item.name === 'string' && item.name.length > 0) {
        return item.name;
    }
    if (typeof item.tool_id === 'string') {
        return item.tool_id;
    }
    return '';
}
