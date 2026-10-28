/**
 * Компонент platform-icon.
 *
 * Загружает SVG через events:
 *   icon/ui_asset/load_requested   { name }       → уж в state.icon.uiCache[name]
 *   icon/file_asset/load_requested { basename }   → state.icon.fileCache[basename]
 *
 * Сам компонент не делает HTTP — это работа icon.effect.
 */
import { html, css } from '../../assets/js/lit/lit.min.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../../assets/js/lit/lit.min.js';
import { unsafeHTML } from '../../assets/js/lit/directives/unsafe-html.min.js';
import { PlatformElement } from '../platform-element/index.js';
import { ICON_EVENTS } from '../events/reducers/icon.js';
import type { PlatformBusState } from '../events/bus-state.js';
import type { SelectController } from '../events/select-controller.js';
import { resolveFileIconBasename } from '../utils/file-icons.js';

export class PlatformIcon extends PlatformElement {
    static override styles: CSSResultGroup = [
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
            /* Monochrome only when not brand/logo. [colored] keeps asset presentation fills. */
            :host(:not([colored]):not([file-icon])) svg { fill: currentColor; }
            :host(:not([colored]):not([file-icon])) svg path { fill: currentColor; }
            :host([colored]:not([file-icon])) {
                /* Brand/logo mode: do not force currentColor onto SVG paints. */
                color: inherit;
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        name: { type: String },
        size: { type: Number },
        filled: { type: Boolean, reflect: true },
        colored: { type: Boolean, reflect: true },
        fileIcon: { type: Boolean, reflect: true, attribute: 'file-icon' },
    };

    declare name: string;
    declare size: number;
    declare filled: boolean;
    declare colored: boolean;
    declare fileIcon: boolean;

    _iconSvgSelect: SelectController<string>;

    constructor() {
        super();
        this.name = '';
        this.size = 20;
        this.filled = false;
        this.colored = false;
        this.fileIcon = false;
        this._iconSvgSelect = this.select((state) => this._selectIconSvg(state));
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('size')) {
            this.style.setProperty('--icon-size', `${this.size}px`);
        }
        if (changed.has('name') || changed.has('fileIcon')) {
            this._requestLoad();
            this.requestUpdate();
        }
    }

    override firstUpdated(): void {
        this._requestLoad();
    }

    _selectIconSvg(state: PlatformBusState): string {
        if (!this.name) {
            return '';
        }
        if (this.fileIcon) {
            const basename = resolveFileIconBasename(this.name);
            const svg = state.icon.fileCache[basename];
            return typeof svg === 'string' ? svg : '';
        }
        const svg = state.icon.uiCache[this.name];
        return typeof svg === 'string' ? svg : '';
    }

    _requestLoad(): void {
        if (!this.name) {
            return;
        }
        const cachedSvg = this._iconSvgSelect.value;
        if (typeof cachedSvg === 'string' && cachedSvg.length > 0) {
            return;
        }
        if (this.fileIcon) {
            const basename = resolveFileIconBasename(this.name);
            this.dispatch(ICON_EVENTS.FILE_LOAD_REQUESTED, { basename });
            return;
        }
        this.dispatch(ICON_EVENTS.UI_LOAD_REQUESTED, { name: this.name });
    }

    _resolveSvg(): string {
        const svg = this._iconSvgSelect.value;
        return typeof svg === 'string' ? svg : '';
    }

    override render(): TemplateResult {
        const svg = this._resolveSvg();
        return html`${unsafeHTML(svg)}`;
    }
}

customElements.define('platform-icon', PlatformIcon);
