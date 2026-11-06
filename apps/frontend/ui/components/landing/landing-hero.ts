/**
 * Hero лендинга — главная секция лендинга
 */
import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import {
    fileListToPublicSearchFiles,
    setPendingPublicSearchFiles,
} from '../../_helpers/public-search-files.js';
import { markPublicSearchLandingTransition } from '../../_helpers/public-search-transition.js';
import { bindInputVisibleInVisualViewport } from '@platform/lib/utils/ensure-input-visible-in-visual-viewport.js';
import { getPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';
import { cosmicTypeStyles } from '@platform/lib/styles/shared/cosmic-marketing.styles.js';
import '@platform/lib/components/platform-icon.js';
import '../cosmic/scramble-text.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const SEARCH_MODES = Object.freeze([
    { key: 'quick', icon: 'search', label: 'hero.search_mode_quick' },
    { key: 'deep', icon: 'layers', label: 'hero.search_mode_deep' },
    { key: 'research', icon: 'sparkle', label: 'hero.search_mode_research' },
]);

export class LandingHero extends PlatformElement {
    static i18nNamespace = 'landing';

    static override properties: PropertyDeclarations = {
        _searchQuery: { state: true },
        _searchMode: { state: true },
        _selectedFiles: { state: true },
    }
    declare _searchQuery: string;
    declare _searchMode: string;
    declare _selectedFiles: File[];
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        cosmicTypeStyles,
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
                min-height: var(--app-vh, 100vh);
                position: relative;
                overflow: hidden;
            }

            .hero-container {
                max-width: 1440px;
                width: 100%;
                margin: 0 auto;
                padding: 0;
                box-sizing: border-box;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: calc(var(--app-vh, 100vh) - 71px);
                position: relative;
            }

            .hero-subtitle {
                display: none;
            }

            .hero-title {
                position: absolute;
                top: 34%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-family: var(--font-display);
                letter-spacing: 0.02em;
                font-weight: 500;
                font-size: clamp(3.5rem, 11vw, 9.5rem);
                line-height: 1;
                text-align: center;
                color: var(--marketing-cosmic-text);
                margin: 0;
                text-transform: uppercase;
                z-index: 12;
                white-space: nowrap;
                pointer-events: none;
                text-shadow: 0 0 60px color-mix(in srgb, var(--marketing-cosmic-cyan) 25%, transparent);
            }

            .hero-image-wrapper {
                display: none;
            }

            .hero-search {
                position: absolute;
                left: 50%;
                top: clamp(480px, calc(var(--app-vh, 100vh) - 260px), 660px);
                bottom: auto;
                transform: translateX(-50%);
                z-index: 24;
                width: min(760px, calc(100% - 40px));
                border-radius: var(--radius-xl);
                padding: 10px;
                box-sizing: border-box;
                background: var(--marketing-cosmic-panel-bg);
                border: 1px solid var(--marketing-cosmic-panel-border);
                box-shadow: var(--marketing-cosmic-panel-shadow);
                backdrop-filter: blur(28px);
            }

            .hero-scroll-hint {
                position: absolute;
                left: var(--space-6);
                bottom: var(--space-6);
                z-index: 20;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-family: var(--font-mono);
                font-size: 11px;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: var(--marketing-cosmic-label);
            }

            .hero-scroll-hint::after {
                content: '';
                display: block;
                width: 42px;
                height: 1px;
                background: var(--marketing-cosmic-line-strong);
            }

            .hero-search-main {
                min-height: 58px;
                display: grid;
                grid-template-columns: 44px minmax(0, 1fr) 44px;
                align-items: center;
                gap: 4px;
            }

            .hero-search-icon {
                display: grid;
                place-items: center;
                color: var(--marketing-cosmic-label);
            }

            input[type='search'] {
                min-width: 0;
                height: 54px;
                border: 0;
                outline: none;
                background: transparent;
                color: var(--marketing-cosmic-text);
                font-family: var(--font-sans);
                font-weight: 500;
                font-size: 20px;
                line-height: 1.2;
                letter-spacing: 0;
            }

            input[type='search']::placeholder {
                color: var(--marketing-cosmic-label);
            }

            .hero-search-submit,
            .hero-tool-icon {
                width: 44px;
                height: 44px;
                border: 0;
                display: grid;
                place-items: center;
                color: var(--marketing-cosmic-bg);
                background: var(--marketing-cosmic-cyan);
                clip-path: var(--marketing-cosmic-btn-clip);
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease, opacity 180ms ease;
            }

            .hero-search-submit:hover {
                background: var(--marketing-cosmic-text);
                transform: translateY(-1px);
            }

            .hero-tool-icon:hover {
                border-color: var(--marketing-cosmic-cyan);
                color: var(--marketing-cosmic-text);
                transform: translateY(-1px);
            }

            .hero-search-submit:disabled,
            .hero-tool-icon:disabled {
                cursor: default;
                opacity: 0.48;
                transform: none;
            }

            .hero-search-tools {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                padding-top: 4px;
            }

            .hero-mode-group,
            .hero-aux-tools {
                display: flex;
                align-items: center;
                gap: 8px;
                min-width: 0;
            }

            .hero-mode-chip {
                height: 36px;
                border: 1px solid var(--marketing-cosmic-panel-border);
                border-radius: var(--radius-full);
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 0 13px;
                color: var(--marketing-cosmic-muted);
                background: transparent;
                font-family: var(--font-mono);
                font-weight: 500;
                font-size: 12px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                line-height: 1;
                white-space: nowrap;
                cursor: pointer;
                transition: transform 180ms ease, color 180ms ease, border-color 180ms ease;
            }

            .hero-mode-chip:hover {
                color: var(--marketing-cosmic-text);
                border-color: var(--marketing-cosmic-panel-border-strong);
                transform: translateY(-1px);
            }

            .hero-mode-chip[aria-pressed='true'] {
                color: var(--marketing-cosmic-cyan);
                border-color: var(--marketing-cosmic-cyan);
                background: var(--marketing-cosmic-glass);
            }

            .hero-tool-icon {
                width: 36px;
                height: 36px;
                background: var(--marketing-cosmic-glass);
                border: 1px solid var(--marketing-cosmic-panel-border);
                color: var(--marketing-cosmic-muted);
            }

            .hero-file-input {
                position: absolute;
                width: 1px;
                height: 1px;
                opacity: 0;
                overflow: hidden;
                clip: rect(0 0 0 0);
                clip-path: inset(50%);
                pointer-events: none;
            }

            .hero-file-list {
                display: flex;
                flex: 1 1 auto;
                flex-wrap: nowrap;
                gap: 8px;
                min-width: 0;
                overflow-x: auto;
                padding: 0;
            }

            .hero-file-chip {
                min-width: 0;
                max-width: 100%;
                height: 34px;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 0 7px 0 10px;
                border-radius: var(--radius-full);
                color: var(--marketing-cosmic-muted);
                background: var(--marketing-cosmic-glass);
                border: 1px solid var(--marketing-cosmic-panel-border);
                box-sizing: border-box;
            }

            .hero-file-label {
                min-width: 0;
                display: inline-flex;
                align-items: baseline;
                gap: 6px;
            }

            .hero-file-name {
                min-width: 0;
                max-width: 210px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font: 500 13px/1 var(--font-sans);
            }

            .hero-file-size {
                flex-shrink: 0;
                color: var(--marketing-cosmic-label);
                font-size: 12px;
                line-height: 1;
            }

            .hero-file-remove {
                width: 24px;
                height: 24px;
                border: 0;
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: var(--marketing-cosmic-muted);
                background: transparent;
                cursor: pointer;
                transition: color 160ms ease, background 160ms ease;
            }

            .hero-file-remove:hover {
                color: var(--marketing-cosmic-text);
                background: var(--marketing-cosmic-glass-strong);
            }

            .hero-text-left {
                position: absolute;
                bottom: 235px;
                left: 50px;
                font-family: var(--font-mono);
                font-size: 14px;
                line-height: 1.5;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--marketing-cosmic-label);
                max-width: 240px;
                z-index: 3;
            }

            .hero-text-right {
                position: absolute;
                bottom: 235px;
                right: 50px;
                font-family: var(--font-mono);
                font-size: 14px;
                line-height: 1.5;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--marketing-cosmic-label);
                max-width: 240px;
                text-align: right;
                z-index: 3;
            }

            .hero-cta-row {
                position: absolute;
                bottom: 38px;
                left: 50%;
                transform: translateX(-50%);
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: center;
                gap: 12px;
                z-index: 11;
                max-width: calc(100% - 32px);
            }

            .hero-cta {
                padding: 14px 28px;
                border: 1px solid var(--marketing-cosmic-cyan);
                border-radius: 0;
                clip-path: var(--marketing-cosmic-btn-clip);
                font-family: var(--font-sans);
                font-weight: 600;
                font-size: 17px;
                line-height: 24px;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                white-space: nowrap;
                box-shadow: 0 0 32px color-mix(in srgb, var(--marketing-cosmic-cyan) 22%, transparent);
                text-align: center;
                text-decoration: none;
                background: var(--marketing-cosmic-cyan);
                color: var(--marketing-cosmic-bg);
            }

            .hero-cta:hover {
                background: var(--marketing-cosmic-text);
                border-color: var(--marketing-cosmic-text);
                transform: translateY(-2px);
            }
            
            @media (max-width: 768px) {
                .hero-subtitle {
                    position: static;
                    transform: none;
                    margin: 16px auto 0;
                    pointer-events: auto;
                }

                .hero-title {
                    position: static;
                    transform: none;
                    font-size: min(80px, calc((100vw - 32px) / 5.2));
                    line-height: 1.05;
                    max-width: calc(100% - 16px);
                    box-sizing: border-box;
                }
            
                .hero-image-wrapper {
                    max-width: 350px;
                }

                .hero-search {
                    position: static;
                    transform: none;
                    width: 100%;
                    max-width: none;
                    order: 2;
                    border-radius: 24px;
                    padding: 8px;
                    margin: 12px 0 0;
                }

                .hero-search-main {
                    grid-template-columns: 38px minmax(0, 1fr) 42px;
                    min-height: 50px;
                }

                input[type='search'] {
                    height: 48px;
                    font-size: 17px;
                }

                .hero-search-tools {
                    align-items: stretch;
                    flex-direction: column;
                }

                .hero-mode-group {
                    overflow-x: auto;
                    padding-bottom: 2px;
                }

                .hero-aux-tools {
                    justify-content: flex-start;
                }

                .hero-file-name {
                    max-width: 180px;
                }
                
                .hero-text-left,
                .hero-text-right {
                    position: static;
                    max-width: 100%;
                    text-align: center;
                    margin: 20px;
                    font-size: 18px;
                }
            
                .hero-cta-row {
                    position: static;
                    transform: none;
                    margin: 20px auto;
                    flex-direction: column;
                    width: min(100%, calc(100vw - 32px));
                }

                .hero-cta {
                    display: block;
                    width: 100%;
                    white-space: normal;
                    box-sizing: border-box;
                    padding: 12px 16px;
                }
                
                .hero-cta:hover {
                    transform: translateY(-2px);
                }
                
                .hero-container {
                    flex-direction: column;
                    justify-content: center;
                    padding: 24px 12px;
                }

                .hero-title {
                    order: 1;
                }

                .hero-subtitle {
                    order: 3;
                }

                .hero-image-wrapper {
                    order: 4;
                }

                .hero-text-left { order: 5; }
                .hero-cta-row { order: 6; }
                .hero-text-right { order: 7; }

                :host-context(html[data-keyboard-visual='1']) .hero-image-wrapper,
                :host-context(html[data-keyboard-visual='1']) .hero-text-left,
                :host-context(html[data-keyboard-visual='1']) .hero-text-right,
                :host-context(html[data-keyboard-visual='1']) .hero-cta-row {
                    display: none;
                }

                :host-context(html[data-keyboard-visual='1']) .hero-title {
                    font-size: min(48px, calc((100vw - 24px) / 5.2));
                    margin-bottom: 4px;
                }

                :host-context(html[data-keyboard-visual='1']) .hero-subtitle {
                    display: none;
                }

                :host-context(html[data-keyboard-visual='1']) .hero-search {
                    position: sticky;
                    top: calc(var(--vv-offset-top, 0px) + 72px);
                    z-index: 20;
                    margin-top: 8px;
                }

                :host-context(html[data-keyboard-visual='1']) .hero-container {
                    padding-bottom: 12px;
                }
            }
            
            @media (min-width: 769px) and (max-width: 1439px) {
                .hero-subtitle {
                    top: 62%;
                }

                .hero-title {
                    font-size: min(200px, calc((100vw - 64px) / 5.2));
                    line-height: 1.1;
                }
                
                .hero-image-wrapper {
                    max-width: 800px;
                }
                
                .hero-text-left {
                    left: 30px;
                    bottom: 225px;
                    font-size: 20px;
                    max-width: 220px;
                }
                
                .hero-text-right {
                    right: 30px;
                    bottom: 225px;
                    font-size: 20px;
                    max-width: 220px;
                }
                
                .hero-search {
                    top: clamp(500px, calc(var(--app-vh, 100vh) - 220px), 620px);
                    bottom: auto;
                }

                .hero-cta-row {
                    bottom: 36px;
                }

                .hero-cta {
                    font-size: 16px;
                    padding: 14px 32px;
                }
            }
            
            @media (min-width: 1440px) {
                .hero-subtitle {
                    top: 60%;
                    font-size: clamp(16px, 1.6vw, 22px);
                    max-width: 800px;
                }

                .hero-title {
                    font-size: clamp(200px, 15vw, 320px);
                    line-height: 1.1;
                }
                
                .hero-image-wrapper {
                    max-width: min(900px, 65vw);
                }
                
                .hero-text-left {
                    left: 48px;
                    bottom: 235px;
                    font-size: 22px;
                    max-width: 270px;
                }
                
                .hero-text-right {
                    right: 48px;
                    bottom: 235px;
                    font-size: 22px;
                    max-width: 270px;
                }
                
                .hero-search {
                    top: clamp(520px, calc(var(--app-vh, 100vh) - 230px), 660px);
                    bottom: auto;
                }

                .hero-cta-row {
                    bottom: 40px;
                }

                .hero-cta {
                    font-size: 18px;
                    padding: 14px 28px;
                }
            }
        `
    ];

    constructor() {
        super();
        this._searchQuery = '';
        this._searchMode = 'quick';
        this._selectedFiles = [];
        /** @type {(() => void) | null} */
        this._releaseSearchInputViewport = null;
    }
    private _releaseSearchInputViewport: (() => void) | null = null;


    override firstUpdated(changedProperties: PropertyValues<this>): void {
        super.firstUpdated(changedProperties);
        this._bindSearchInputViewport();
    }

    override disconnectedCallback(): void {
        if (this._releaseSearchInputViewport !== null) {
            this._releaseSearchInputViewport();
            this._releaseSearchInputViewport = null;
        }
        super.disconnectedCallback();
    }

    _bindSearchInputViewport() {
        const root = this.renderRoot;
        if (!root) {
            return;
        }
        const input = root.querySelector('[data-role="hero-search-input"]');
        if (!(input instanceof HTMLInputElement)) {
            return;
        }
        if (this._releaseSearchInputViewport !== null) {
            this._releaseSearchInputViewport();
        }
        this._releaseSearchInputViewport = bindInputVisibleInVisualViewport(input);
    }

    _handleCTA = () => {
        this.navigate('digital-workers');
    };

    _isMode(value: unknown) {
        return value === 'quick' || value === 'deep' || value === 'research';
    }

    _setSearchMode(mode: string) {
        if (!this._isMode(mode)) {
            throw new Error(`Invalid search mode: ${mode}`);
        }
        this._searchMode = mode;
    }

    _handleSearchInput(event: Event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('landing-hero: search input required');
        }
        this._searchQuery = target.value;
    }

    _fileErrorMessage(error: any) {
        if (error instanceof Error && typeof error.message === 'string' && error.message !== '') {
            return error.message;
        }
        return String(error);
    }

    _openFilePicker() {
        const input = this.renderRoot.querySelector('[data-role="hero-search-files"]');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('LandingHero: file input not found');
        }
        input.click();
    }

    _handleFilesSelected(event: Event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('LandingHero: file input event target required');
        }
        try {
            const files = fileListToPublicSearchFiles(target.files);
            if (files.length > 0) {
                this._selectedFiles = [...this._selectedFiles, ...files];
            }
        } catch (error) {
            this.toast('hero.file_upload_error', {
                type: 'error',
                vars: { message: this._fileErrorMessage(error) },
            });
        }
        target.value = '';
    }

    _removeFile(index: number) {
        if (!Number.isInteger(index) || index < 0 || index >= this._selectedFiles.length) {
            throw new Error('LandingHero._removeFile: index out of range');
        }
        this._selectedFiles = this._selectedFiles.filter((_, itemIndex) => itemIndex !== index);
    }

    _submitSearch(event: Event) {
        event.preventDefault();
        const query = this._searchQuery.trim();
        if (query === '') {
            if (this._selectedFiles.length > 0) {
                this.toast('hero.file_query_required', { type: 'warning' });
            }
            return;
        }
        const mode = this._searchMode;
        if (this._selectedFiles.length > 0) {
            setPendingPublicSearchFiles(this._selectedFiles);
        }
        markPublicSearchLandingTransition(query, mode);
        this.navigate('search', {}, {
            search: `?q=${encodeURIComponent(query)}&mode=${encodeURIComponent(mode)}`,
        });
    }

    _renderModeChip(mode: { key: string; icon: string; label: string }) {
        const active = this._searchMode === mode.key;
        return html`
            <button
                class="hero-mode-chip"
                type="button"
                aria-pressed=${active ? 'true' : 'false'}
                @click=${() => this._setSearchMode(mode.key)}
            >
                <platform-icon name=${mode.icon} size="15"></platform-icon>
                <span>${this.t(mode.label)}</span>
            </button>
        `;
    }

    _renderSelectedFile(file: File, index: number) {
        return html`
            <div class="hero-file-chip" role="listitem">
                <platform-icon file-icon name=${resolveFileIconKey(typeof file.name === 'string' ? file.name : '', typeof file.type === 'string' ? file.type : '')} size="18"></platform-icon>
                <span class="hero-file-label">
                    <span class="hero-file-name" title=${file.name}>${file.name}</span>
                    <span class="hero-file-size">${formatFileSize(file.size)}</span>
                </span>
                <button
                    class="hero-file-remove"
                    type="button"
                    title=${this.t('hero.remove_file')}
                    aria-label=${this.t('hero.remove_file')}
                    @click=${() => this._removeFile(index)}
                >
                    <platform-icon name="close" size="14"></platform-icon>
                </button>
            </div>
        `;
    }

    _renderSelectedFiles() {
        if (this._selectedFiles.length === 0) {
            return nothing;
        }
        return html`
            <div class="hero-file-list" role="list" aria-label=${this.t('hero.selected_files')}>
                ${this._selectedFiles.map((file, index) => this._renderSelectedFile(file, index))}
            </div>
        `;
    }

    _renderSearch() {
        return html`
            <form class="hero-search" @submit=${this._submitSearch}>
                <div class="hero-search-main">
                    <span class="hero-search-icon"><platform-icon name="search" size="22"></platform-icon></span>
                    <input
                        type="search"
                        data-role="hero-search-input"
                        autocomplete="off"
                        spellcheck="true"
                        .value=${this._searchQuery}
                        placeholder=${this.t('hero.search_placeholder')}
                        aria-label=${this.t('hero.search_aria')}
                        @input=${this._handleSearchInput}
                    />
                    <button class="hero-search-submit" type="submit" aria-label=${this.t('hero.search_submit')}>
                        <platform-icon name="send" size="18"></platform-icon>
                    </button>
                </div>
                <div class="hero-search-tools">
                    <div class="hero-mode-group" role="group" aria-label=${this.t('hero.search_modes')}>
                        ${SEARCH_MODES.map((mode) => this._renderModeChip(mode))}
                    </div>
                    ${this._renderSelectedFiles()}
                    <div class="hero-aux-tools" aria-label=${this.t('hero.search_tools')}>
                        <input
                            class="hero-file-input"
                            data-role="hero-search-files"
                            type="file"
                            multiple
                            @change=${this._handleFilesSelected}
                        />
                        <button
                            class="hero-tool-icon"
                            type="button"
                            title=${this.t('hero.files_tool')}
                            aria-label=${this.t('hero.files_tool')}
                            @click=${this._openFilePicker}
                        >
                            <platform-icon name="paperclip" size="17"></platform-icon>
                        </button>
                    </div>
                </div>
            </form>
        `;
    }

    override render(): TemplateResult {
        const t = (key: string) => this.t(key);
        const brand = getPlatformBrandBootstrap();
        const heroWordmark = (brand === undefined || brand === null || typeof brand.platformName !== 'string' ? '' : brand.platformName).toUpperCase();
        return html`
            <div class="hero-container">
                <h1 class="hero-title"><scramble-text .text=${heroWordmark}></scramble-text></h1>
                <p class="hero-subtitle">${t('hero.subtitle')}</p>

                ${this._renderSearch()}

                <p class="hero-text-left">
                    ${unsafeHTML(t('hero.trust_process'))}
                        </p>

                        <div class="hero-cta-row">
                            <button type="button" class="hero-cta" @click=${this._handleCTA}>
                                ${t('hero.start_button')}
                            </button>
                        </div>

                <p class="hero-text-right">
                    ${unsafeHTML(t('hero.evolution'))}
                        </p>

                <span class="hero-scroll-hint">${t('cosmic.scroll_hint')}</span>
            </div>
        `;
    }
}

customElements.define('landing-hero', LandingHero);
