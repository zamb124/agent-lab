/**
 * Иконки и visual kind для карточек реестра tools/flows (picker, шаблоны code-ноды).
 */

import { html } from 'lit';
import { getNodeTypeMeta } from './node-icons.js';
import { inferToolRefLanguage } from './flows-tool-visual.js';
import { renderMcpServerIcon } from './mcp-server-icon.js';
import type {TemplateResult} from 'lit';

const MCP_CODE_MODE = 'mcp_tool';

const TAG_GROUP_ICONS = Object.freeze({
    crm: 'users',
    documents: 'file-text',
    files: 'folder',
    sync: 'chat',
    worktracker: 'checklist',
    web: 'globe',
    knowledge: 'book-open',
    scheduling: 'schedule',
    google_docs: 'file-text',
    google_sheets: 'chart',
    viz: 'image',
    flows: 'workflow',
    device: 'apps',
    text: 'text-fields',
    misc: 'layers',
    mcp: 'mcp',
    flow: 'workflow',
});

/**
 * @param {Record<string, unknown>} item
 * @returns {boolean}
 */
function _hasInlineCode(item: any) {
    return typeof item.code === 'string' && item.code.trim().length > 0;
}

/**
 * @param {Record<string, unknown>} item
 * @returns {boolean}
 */
function _isMcpItem(item: any) {
    const mcpId = item.mcp_server_id;
    if (typeof mcpId === 'string' && mcpId.length > 0) {
        return true;
    }
    if (item.code_mode === MCP_CODE_MODE) {
        return true;
    }
    const toolId = item.tool_id;
    return typeof toolId === 'string' && toolId.startsWith('mcp:');
}

/**
 * @param {Record<string, unknown>} item — элемент из /tools или /tools/all
 * @returns {'flow' | 'mcp' | 'code' | 'tool'}
 */
export function registryItemVisualKind(item: any) {
    if (!item || typeof item !== 'object') {
        throw new Error('flows-registry-item-icon: item required');
    }
    if (item.item_type === 'flow') {
        return 'flow';
    }
    if (_isMcpItem(item)) {
        return 'mcp';
    }
    if (_hasInlineCode(item)) {
        return 'code';
    }
    return 'tool';
}

/**
 * Язык для code-карточки; пустая строка — показать generic code icon.
 * @param {Record<string, unknown>} item
 * @returns {string}
 */
export function registryItemLanguage(item: any) {
    if (registryItemVisualKind(item) !== 'code') {
        return '';
    }
    return inferToolRefLanguage(item);
}

/**
 * @param {string} tag
 * @returns {string} имя иконки для platform-icon
 */
export function tagGroupIconName(tag: any) {
    if (typeof tag !== 'string' || tag.length === 0) {
        throw new Error('flows-registry-item-icon: tag required');
    }
    const mapped = (TAG_GROUP_ICONS as any)[tag];
    if (typeof mapped === 'string' && mapped.length > 0) {
        return mapped;
    }
    return 'layers';
}

/**
 * Primary tag icon for builtin tool cards (без inline code).
 * @param {Record<string, unknown>} item
 * @returns {string}
 */
export function registryItemPrimaryTagIcon(item: any) {
    if (!item || typeof item !== 'object') {
        throw new Error('flows-registry-item-icon: item required');
    }
    const tags = item.tags;
    if (Array.isArray(tags)) {
        for (const tag of tags) {
            if (typeof tag === 'string' && tag.length > 0 && (TAG_GROUP_ICONS as any)[tag]) {
                return (TAG_GROUP_ICONS as any)[tag];
            }
        }
    }
    return 'tool';
}

/**
 * @param {Record<string, unknown>} item — элемент из /tools или /tools/all
 * @returns {string} имя иконки для platform-icon
 */
export function registryItemIconName(item: any) {
    const kind = registryItemVisualKind(item);
    if (kind === 'flow') {
        return getNodeTypeMeta('flow').icon;
    }
    if (kind === 'mcp') {
        return getNodeTypeMeta('mcp').icon;
    }
    if (kind === 'code') {
        return getNodeTypeMeta('code').icon;
    }
    return registryItemPrimaryTagIcon(item);
}

/**
 * Заголовок карточки: title для tool/flow API.
 * @param {Record<string, unknown>} item
 * @returns {string}
 */
export function registryItemTitle(item: any) {
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

/**
 * Слот-иконка для picker-карточки (lib-card-icon + language/MCP/tag).
 *
 * @param {Record<string, unknown>} item
 * @param {{ size?: number, server?: Record<string, unknown> | null }} [options]
 * @returns {import('lit').TemplateResult}
 */
export function renderRegistryItemCardIcon(item: any, options = {}) {
    const kind = registryItemVisualKind(item);
    const size = typeof (options as Record<string, any>).size === 'number' && (options as Record<string, any>).size > 0 ? (options as Record<string, any>).size : 22;
    const language = registryItemLanguage(item);
    let inner;
    if (kind === 'mcp') {
        const server = (options as Record<string, any>).server;
        if (server && typeof server === 'object') {
            inner = renderMcpServerIcon(server, size);
        } else {
            inner = html`<platform-icon name=${registryItemIconName(item)} size=${size}></platform-icon>`;
        }
    } else if (kind === 'code' && (language as any).length > 0) {
        inner = html`<flows-code-language-icon language=${language} size=${size}></flows-code-language-icon>`;
    } else {
        inner = html`<platform-icon name=${registryItemIconName(item)} size=${size}></platform-icon>`;
    }
    return html`
        <div class="lib-card-icon" data-kind=${kind} aria-hidden="true">
            ${inner}
        </div>
    `;
}
