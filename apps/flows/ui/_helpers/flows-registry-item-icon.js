/**
 * Иконки для карточек реестра tools/flows (picker, шаблоны code-ноды).
 */

import { getNodeTypeMeta } from '../constants/node-icons.js';

/**
 * @param {Record<string, unknown>} item — элемент из /tools или /tools/all
 * @returns {string} имя иконки для platform-icon
 */
export function registryItemIconName(item) {
    if (!item || typeof item !== 'object') {
        throw new Error('flows-registry-item-icon: item required');
    }
    const itemType = item.item_type;
    if (itemType === 'flow') {
        return getNodeTypeMeta('flow').icon;
    }
    const mcpId = item.mcp_server_id;
    if (typeof mcpId === 'string' && mcpId.length > 0) {
        return getNodeTypeMeta('mcp').icon;
    }
    return getNodeTypeMeta('code').icon;
}

/**
 * Заголовок карточки: title для tool/flow API.
 * @param {Record<string, unknown>} item
 * @returns {string}
 */
export function registryItemTitle(item) {
    if (!item || typeof item !== 'object') {
        throw new Error('flows-registry-item-icon: item required');
    }
    const title = item.title;
    if (typeof title === 'string' && title.length > 0) {
        return title;
    }
    const id = item.tool_id;
    if (typeof id === 'string' && id.length > 0) {
        return id;
    }
    return '';
}
