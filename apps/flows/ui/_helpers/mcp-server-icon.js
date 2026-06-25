/**
 * Иконки MCP серверов: icon_url из API, static fallback, generic mcp icon.
 */

import { html } from 'lit';

export const MCP_LOGO_BASE = '/static/core/assets/mcp_logos';

const STATIC_MCP_LOGO_SLUGS = Object.freeze(['browser', 'search']);

/**
 * @param {Record<string, unknown> | null | undefined} server
 * @returns {string | null}
 */
export function resolveMcpServerIconUrl(server) {
    if (server && typeof server === 'object') {
        const iconUrl = server.icon_url;
        if (typeof iconUrl === 'string' && iconUrl.length > 0) {
            return iconUrl;
        }
        const serverId = server.server_id;
        if (typeof serverId === 'string' && STATIC_MCP_LOGO_SLUGS.includes(serverId)) {
            return `${MCP_LOGO_BASE}/${serverId}.svg`;
        }
    }
    return null;
}

/**
 * @param {Record<string, unknown> | null | undefined} server
 * @param {number} [size]
 * @returns {import('lit').TemplateResult}
 */
export function renderMcpServerIcon(server, size = 24) {
    const iconUrl = resolveMcpServerIconUrl(server);
    if (iconUrl) {
        return html`
            <img
                class="mcp-server-icon-img"
                src=${iconUrl}
                alt=""
                width=${size}
                height=${size}
                loading="lazy"
            />
        `;
    }
    return html`<platform-icon name="mcp" size=${String(size)}></platform-icon>`;
}
