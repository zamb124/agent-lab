/**
 * Platform Icon Component.
 *
 * Загружает SVG через events:
 *   icon/ui_asset/load_requested   { name }       → уж в state.icon.uiCache[name]
 *   icon/file_asset/load_requested { basename }   → state.icon.fileCache[basename]
 *
 * Сам компонент не делает HTTP — это работа icon.effect.
 */
import { html, css } from '../../assets/js/lit/lit.min.js';
import { unsafeHTML } from '../../assets/js/lit/directives/unsafe-html.min.js';
import { PlatformElement } from '../platform-element/index.js';
import { ICON_EVENTS } from '../events/reducers/icon.js';
import { resolveFileIconBasename } from '../utils/file-icons.js';

export class PlatformIcon extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: var(--icon-size, 20px);
                height: var(--icon-size, 20px);
                color: inherit;
            }
            svg { width: 100%; height: 100%; }
            :host(:not([colored]):not([file-icon])) svg { fill: currentColor; }
            :host(:not([colored]):not([file-icon])) svg path { fill: currentColor; }
        `,
    ];

    static properties = {
        name: { type: String },
        size: { type: Number },
        filled: { type: Boolean, reflect: true },
        colored: { type: Boolean, reflect: true },
        fileIcon: { type: Boolean, reflect: true, attribute: 'file-icon' },
    };

    constructor() {
        super();
        this.name = '';
        this.size = 20;
        this.filled = false;
        this.colored = false;
        this.fileIcon = false;
        this._iconCacheSelect = this.select((s) => s.icon);
    }

    updated(changed) {
        if (changed.has('size')) {
            this.style.setProperty('--icon-size', `${this.size}px`);
        }
        if (changed.has('name') || changed.has('fileIcon')) {
            this._requestLoad();
        }
    }

    firstUpdated() {
        this._requestLoad();
    }

    _requestLoad() {
        if (!this.name) return;
        const iconState = this._iconCacheSelect.value || { uiCache: {}, fileCache: {} };
        if (this.fileIcon) {
            try {
                const basename = resolveFileIconBasename(this.name);
                if (iconState.fileCache[basename]) return;
                this.dispatch(ICON_EVENTS.FILE_LOAD_REQUESTED, { basename });
            } catch (err) {
                console.warn(`[platform-icon] file icon "${this.name}":`, err.message);
            }
            return;
        }
        if (iconState.uiCache[this.name]) return;
        this.dispatch(ICON_EVENTS.UI_LOAD_REQUESTED, { name: this.name });
    }

    _resolveSvg() {
        if (!this.name) return '';
        const iconState = this._iconCacheSelect.value || { uiCache: {}, fileCache: {} };
        if (this.fileIcon) {
            try {
                const basename = resolveFileIconBasename(this.name);
                return iconState.fileCache[basename] || '';
            } catch {
                return '';
            }
        }
        return iconState.uiCache[this.name] || '';
    }

    render() {
        const svg = this._resolveSvg();
        return html`${unsafeHTML(svg)}`;
    }
}

customElements.define('platform-icon', PlatformIcon);
