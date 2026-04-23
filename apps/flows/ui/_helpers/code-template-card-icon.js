/**
 * Иконка карточки шаблона в каталоге code-ноды: единая с типом ноды `code`.
 */

import { getNodeTypeMeta } from '../constants/node-icons.js';

/**
 * @param {Record<string, unknown>} _t — шаблон из code/templates (резерв для контракта)
 * @returns {string} имя иконки для platform-icon
 */
export function codeTemplateCardIconName(_t) {
    return getNodeTypeMeta('code').icon;
}
