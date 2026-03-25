/**
 * Строка пространства в сайдбаре: аватар и имя (внутри nav-row-wrap + шестерёнка снаружи).
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { hueFromString } from '../utils/sync-hue.js';

export class SyncSpaceRow extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                box-sizing: border-box;
            }

            button.nav-item {
                position: relative;
                box-sizing: border-box;
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                cursor: pointer;
                background: transparent;
                border: none;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                width: 100%;
                text-align: left;
                transition: all var(--duration-fast);
                margin-bottom: 0;
            }

            button.nav-item:hover {
                background: transparent;
                border-color: transparent;
                color: inherit;
            }

            button.nav-item.active {
                background: transparent;
                border-color: transparent;
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            :host([icon-only]) button.nav-item {
                justify-content: center;
                align-items: center;
                padding: var(--space-2) var(--space-1);
            }

            :host([icon-only]) .nav-item-main {
                flex: 0 0 auto;
                min-width: 0;
            }

            :host([icon-only]) .nav-item-label {
                display: none !important;
            }

            .nav-item-label {
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }

            .entity-avatar {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                flex-shrink: 0;
                object-fit: cover;
            }

            .entity-avatar-initials {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: var(--font-semibold);
                color: #fff;
            }

            .nav-item-main {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
            }
        `,
    ];

    static properties = {
        space: { type: Object },
        active: { type: Boolean },
        iconOnly: { type: Boolean, attribute: 'icon-only', reflect: true },
    };

    constructor() {
        super();
        this.space = null;
        this.active = false;
        this.iconOnly = false;
    }

    _spaceAvatar(space) {
        const url = space.avatar_url;
        if (typeof url === 'string' && url !== '') {
            return html`<img class="entity-avatar" src=${url} alt="" />`;
        }
        const label = typeof space.name === 'string' && space.name !== '' ? space.name : space.id;
        const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
        const hue = hueFromString(space.id);
        return html`
            <span class="entity-avatar-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
        `;
    }

    render() {
        const space = this.space;
        if (!space) {
            return html``;
        }
        const title = typeof space.name === 'string' && space.name !== '' ? space.name : space.id;
        const btnClass = classMap({
            'nav-item': true,
            'nav-item--in-wrap': true,
            active: this.active,
        });
        return html`
            <button type="button" class=${btnClass}>
                <div class="nav-item-main">
                    ${this._spaceAvatar(space)}
                    <span class="nav-item-label">${title}</span>
                </div>
            </button>
        `;
    }
}

customElements.define('sync-space-row', SyncSpaceRow);
