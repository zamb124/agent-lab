/**
 * Стабильный рендерер логотипов языков для изолированных code runner-ов.
 *
 * `platform-icon` загружает SVG через платформенный кэш иконок. Для логотипов языков
 * в плотных пикерах и canvas-chip-ах нужен детерминированный первый paint, поэтому
 * этот компонент напрямую рендерит общие официальные SVG-ассеты.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveUiIconFile } from '@platform/lib/utils/file-icons.js';
import {
    flowCodeLanguageIconName,
    flowCodeLanguageShortLabel,
    normalizeFlowCodeLanguage,
} from '../../_helpers/flows-code-languages.js';

export class FlowsCodeLanguageIcon extends PlatformElement {
    static properties = {
        language: { type: String, reflect: true },
        size: { type: Number },
        _failed: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                --flows-code-language-icon-size: 20px;
                display: inline-flex;
                width: auto;
                height: auto;
                align-items: center;
                justify-content: center;
                flex: 0 0 auto;
                line-height: 1;
                vertical-align: middle;
            }
            .icon {
                width: var(--flows-code-language-icon-size);
                height: var(--flows-code-language-icon-size);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 0;
                min-height: 0;
            }
            img {
                display: block;
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            .icon[data-language='javascript'] img,
            .icon[data-language='typescript'] img {
                width: 82%;
                height: 82%;
                border-radius: calc(var(--flows-code-language-icon-size) * 0.16);
            }
            .fallback {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 100%;
                color: var(--text-primary);
                font-size: max(10px, calc(var(--flows-code-language-icon-size) * 0.42));
                font-weight: var(--font-bold);
                letter-spacing: 0;
                white-space: nowrap;
            }
        `,
    ];

    constructor() {
        super();
        this.language = 'python';
        this.size = 20;
        this._failed = false;
    }

    updated(changed) {
        if (changed.has('language')) {
            this._failed = false;
        }
    }

    _normalizedLanguage() {
        return normalizeFlowCodeLanguage(this.language);
    }

    _normalizedSize() {
        const size = Number(this.size);
        if (Number.isFinite(size) && size > 0) {
            return size;
        }
        return 20;
    }

    _assetSrc(language) {
        const iconName = flowCodeLanguageIconName(language);
        const file = resolveUiIconFile(iconName);
        return `/static/core/assets/icons/${file}.svg`;
    }

    _onImageError() {
        this._failed = true;
    }

    render() {
        const language = this._normalizedLanguage();
        const size = this._normalizedSize();
        const style = `--flows-code-language-icon-size: ${size}px;`;
        return html`
            <span class="icon" data-language=${language} style=${style}>
                ${this._failed
                    ? html`<span class="fallback">${flowCodeLanguageShortLabel(language)}</span>`
                    : html`<img
                        src=${this._assetSrc(language)}
                        alt=""
                        draggable="false"
                        @error=${this._onImageError}
                    >`}
            </span>
        `;
    }
}

customElements.define('flows-code-language-icon', FlowsCodeLanguageIcon);
