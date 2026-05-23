/**
 * platform-services-launcher — сетка быстрого запуска продуктов платформы.
 * Каталог: platform-services-catalog. Навигация: build-service-entry-url.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { PLATFORM_SERVICES } from '../utils/platform-services-catalog.js';
import { buildServiceEntryUrl, isStandalonePwaMode } from '../utils/build-service-entry-url.js';

const HEALTH_DOT = {
    healthy: 'var(--success)',
    unhealthy: 'var(--error)',
    loading: 'var(--text-tertiary)',
};
const SYSTEM_ONLY_SERVICE_IDS = new Set(['grafana', 'litserve']);

export class PlatformServicesLauncher extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        /** menu | page | compact */
        layout: { type: String },
        /** default: сам переход; event-only: только service-launch (модалка). */
        navigateMode: { type: String, attribute: 'navigate-mode' },
        healthByServiceId: { type: Object, attribute: 'health-by-service-id' },
        disabledById: { type: Object, attribute: 'disabled-by-id' },
        /** Непустой массив id из каталога — только эти плитки, в заданном порядке. */
        includeServiceIds: { type: Array, attribute: false },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
            }
            :host([layout="menu"]) .grid,
            :host([layout="compact"]) .grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }
            :host([layout="page"]) .grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
                min-width: 0;
                width: 100%;
            }
            @media (max-width: 600px) {
                :host([layout="page"]) .grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            @media (min-width: 900px) {
                :host([layout="page"]) .grid {
                    grid-template-columns: repeat(4, minmax(0, 1fr));
                }
            }
            .tile {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
                text-align: center;
                text-decoration: none;
                color: inherit;
                padding: var(--space-2);
                border-radius: var(--radius-xl);
                transition:
                    transform var(--duration-normal) var(--easing-default),
                    box-shadow var(--duration-normal) var(--easing-default),
                    background var(--duration-normal) var(--easing-default);
                border: none;
                background: transparent;
                font: inherit;
                cursor: pointer;
                box-sizing: border-box;
            }
            a.tile {
                text-decoration: none;
            }
            @media (hover: hover) {
                a.tile:not(:active):hover,
                button.tile:not(:active):hover {
                    transform: translateY(-4px);
                    background: color-mix(in srgb, var(--glass-solid-medium) 65%, transparent);
                    box-shadow:
                        0 1px 0 0 color-mix(in srgb, var(--text-primary) 12%, transparent),
                        0 8px 20px -4px color-mix(in srgb, var(--text-primary) 18%, transparent),
                        0 16px 40px -12px color-mix(in srgb, var(--accent) 25%, transparent);
                }
            }
            a.tile:active,
            button.tile:active {
                transform: scale(0.97) translateY(0);
            }
            .icon-wrap {
                position: relative;
                width: 64px;
                height: 64px;
                border-radius: var(--radius-2xl);
                background: linear-gradient(
                    145deg,
                    color-mix(in srgb, var(--brand-from) 35%, var(--glass-solid-medium)) 0%,
                    color-mix(in srgb, var(--brand-to) 28%, var(--glass-solid-medium)) 100%
                );
                border: 1px solid var(--glass-border-medium);
                box-shadow: var(--glass-shadow-medium);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2);
                transition:
                    transform var(--duration-normal) var(--easing-default),
                    box-shadow var(--duration-normal) var(--easing-default),
                    border-color var(--duration-normal) var(--easing-default);
            }
            @media (hover: hover) {
                a.tile:not(:active):hover .icon-wrap,
                button.tile:not(:active):hover .icon-wrap {
                    transform: translateY(-2px) scale(1.04);
                    border-color: color-mix(in srgb, var(--brand-from) 40%, var(--glass-border-medium));
                    box-shadow:
                        var(--glass-inner-glow-medium),
                        0 1px 2px color-mix(in srgb, var(--text-primary) 12%, transparent),
                        0 6px 14px -2px color-mix(in srgb, var(--text-primary) 20%, transparent),
                        0 12px 28px -8px color-mix(in srgb, var(--brand-from) 35%, transparent);
                }
            }
            a.tile:focus-visible,
            button.tile:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 3px;
            }
            a.tile:focus-visible:not(:active),
            button.tile:focus-visible:not(:active) {
                transform: translateY(-2px);
                background: color-mix(in srgb, var(--glass-solid-medium) 55%, transparent);
            }
            a.tile:focus-visible:not(:active) .icon-wrap,
            button.tile:focus-visible:not(:active) .icon-wrap {
                transform: translateY(-1px) scale(1.02);
                box-shadow:
                    var(--glass-inner-glow-subtle),
                    0 4px 12px -2px color-mix(in srgb, var(--text-primary) 16%, transparent);
            }
            :host([layout="menu"]) .icon-wrap,
            :host([layout="compact"]) .icon-wrap {
                width: 56px;
                height: 56px;
            }
            .icon-wrap img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            .health-dot {
                position: absolute;
                top: 4px;
                right: 4px;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: var(--health-dot-color);
                box-shadow: 0 0 6px var(--health-dot-color);
                border: 2px solid var(--glass-solid-medium);
            }
            .label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.25;
                max-width: 100%;
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
            }
            .tile--disabled {
                cursor: not-allowed;
                pointer-events: none;
                opacity: 0.72;
            }
        `,
    ];

    constructor() {
        super();
        this.layout = 'page';
        this.navigateMode = 'default';
        this.healthByServiceId = null;
        this.disabledById = null;
        this.includeServiceIds = null;
        this._activeCompanyId = this.select((s) => s.auth.activeCompanyId);
    }

    _servicesToRender() {
        const activeCompanyId = this._activeCompanyId.value;
        const isSystemCompany = activeCompanyId === 'system';
        const ids = this.includeServiceIds;
        if (Array.isArray(ids) && ids.length > 0) {
            return ids.map((id) => {
                const s = PLATFORM_SERVICES.find((x) => x.id === id);
                if (!s) {
                    throw new Error(`platform-services-launcher: unknown service id "${id}"`);
                }
                return s;
            }).filter((s) => isSystemCompany || !SYSTEM_ONLY_SERVICE_IDS.has(s.id));
        }
        return PLATFORM_SERVICES.filter((s) => isSystemCompany || !SYSTEM_ONLY_SERVICE_IDS.has(s.id));
    }

    _healthForItem(id) {
        const m = this.healthByServiceId;
        if (m && typeof m === 'object' && typeof m[id] === 'string') {
            return m[id];
        }
        if (id === 'litserve' && this._activeCompanyId.value !== 'system') {
            return 'unhealthy';
        }
        return 'healthy';
    }

    _disabledForItem(id) {
        const m = this.disabledById;
        if (m && typeof m === 'object' && typeof m[id] === 'boolean') {
            return m[id];
        }
        return id === 'litserve' && this._activeCompanyId.value !== 'system';
    }

    _navigate(serviceId) {
        if (this.navigateMode === 'event-only') {
            this.emit('service-launch', { serviceId });
            return;
        }
        const url = buildServiceEntryUrl(serviceId);
        if (isStandalonePwaMode()) {
            window.location.href = url;
        } else {
            window.open(url, '_blank', 'noopener,noreferrer');
        }
    }

    _onTileClick(e, serviceId) {
        e.preventDefault();
        e.stopPropagation();
        if (this._disabledForItem(serviceId)) {
            return;
        }
        this._navigate(serviceId);
    }

    _renderTile(svc) {
        const id = svc.id;
        const disabled = this._disabledForItem(id);
        const healthState = this._healthForItem(id);
        const dotColor = HEALTH_DOT[healthState];
        const brandStyle = `--brand-from: ${svc.brandFrom}; --brand-to: ${svc.brandTo}; --health-dot-color: ${dotColor};`;
        const title = this.t(svc.nameKey, null, 'platform');
        const iconBlock = html`
            <div class="icon-wrap" style=${brandStyle}>
                <span class="health-dot" aria-hidden="true"></span>
                <img src=${svc.logoSrc} alt="" />
            </div>
        `;
        const label = html`<span class="label">${title}</span>`;
        if (disabled) {
            return html`
                <div class="tile tile--disabled" data-service-id=${id} style=${brandStyle} aria-label=${title}>
                    ${iconBlock}
                    ${label}
                </div>
            `;
        }
        if (this.navigateMode === 'event-only') {
            return html`
                <button
                    type="button"
                    class="tile"
                    data-service-id=${id}
                    style=${brandStyle}
                    aria-label=${title}
                    @click=${(e) => this._onTileClick(e, id)}
                >
                    ${iconBlock}
                    ${label}
                </button>
            `;
        }
        const href = buildServiceEntryUrl(id);
        return html`
            <a
                class="tile"
                data-service-id=${id}
                href=${href}
                aria-label=${title}
                style=${brandStyle}
                @click=${(e) => {
                    e.stopPropagation();
                    if (isStandalonePwaMode()) {
                        e.preventDefault();
                        this._onTileClick(e, id);
                    }
                }}
            >
                ${iconBlock}
                ${label}
            </a>
        `;
    }

    render() {
        const rows = this._servicesToRender();
        return html`
            <div class="grid" part="grid">
                ${rows.map((svc) => this._renderTile(svc))}
            </div>
        `;
    }
}

customElements.define('platform-services-launcher', PlatformServicesLauncher);
