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
} from '../../utils/public-search-files.js';
import { markPublicSearchLandingTransition } from '../../utils/public-search-transition.js';
import '@platform/lib/components/platform-icon.js';

const SEARCH_MODES = Object.freeze([
    { key: 'quick', icon: 'search', label: 'hero.search_mode_quick' },
    { key: 'deep', icon: 'layers', label: 'hero.search_mode_deep' },
    { key: 'research', icon: 'sparkle', label: 'hero.search_mode_research' },
]);

export class LandingHero extends PlatformElement {
    static i18nNamespace = 'landing';

    static properties = {
        _searchQuery: { state: true },
        _searchMode: { state: true },
        _selectedFiles: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
                min-height: var(--app-vh, 100vh);
                position: relative;
                overflow: hidden;
                background: var(--landing-hero-bg, #0F0F0F);
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
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-family: 'Fira Sans Condensed', sans-serif;
                font-weight: 500;
                font-size: 280px;
                line-height: 320px;
                text-align: center;
                color: var(--landing-primary, #5768FE);
                margin: 0;
                text-transform: capitalize;
                z-index: 1;
                white-space: nowrap;
            }
            
            .hero-image-wrapper {
                position: relative;
                z-index: 10;
                width: 100%;
                max-width: 1200px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .hero-image {
                width: 100%;
                height: auto;
                object-fit: contain;
                filter: var(--landing-hero-image-filter, drop-shadow(0 0 60px rgba(87, 104, 254, 0.4)));
            }

            .hero-search {
                position: absolute;
                left: 50%;
                top: clamp(520px, calc(var(--app-vh, 100vh) - 230px), 660px);
                bottom: auto;
                transform: translateX(-50%);
                z-index: 24;
                width: min(760px, calc(100% - 40px));
                border-radius: 30px;
                padding: 10px;
                box-sizing: border-box;
                background: var(--landing-search-bg, rgba(29, 29, 29, 0.9));
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.11));
                box-shadow: var(--landing-search-shadow, 0 26px 90px rgba(0, 0, 0, 0.44));
                backdrop-filter: blur(28px);
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
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.66));
            }

            input[type='search'] {
                min-width: 0;
                height: 54px;
                border: 0;
                outline: none;
                background: transparent;
                color: var(--landing-text, #fff);
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 20px;
                line-height: 1.2;
                letter-spacing: 0;
            }

            input[type='search']::placeholder {
                color: var(--landing-text-faint, rgba(232, 232, 232, 0.48));
            }

            .hero-search-submit,
            .hero-tool-icon {
                width: 44px;
                height: 44px;
                border: 0;
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: var(--landing-on-primary, #fff);
                background: var(--landing-primary, #5768FE);
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease, opacity 180ms ease;
            }

            .hero-search-submit:hover,
            .hero-tool-icon:hover {
                background: #6877ff;
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
                border: 0;
                border-radius: 999px;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 0 13px;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.74));
                background: var(--landing-panel-bg-strong, rgba(255, 255, 255, 0.07));
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 14px;
                line-height: 1;
                white-space: nowrap;
                cursor: pointer;
                transition: transform 180ms ease, color 180ms ease, background 180ms ease;
            }

            .hero-mode-chip:hover {
                color: var(--landing-text, #fff);
                background: var(--landing-panel-border-strong, rgba(255, 255, 255, 0.13));
                transform: translateY(-1px);
            }

            .hero-mode-chip[aria-pressed='true'] {
                color: var(--landing-on-primary, #fff);
                background: rgba(87, 104, 254, 0.36);
                box-shadow: inset 0 0 0 1px rgba(137, 149, 255, 0.36);
            }

            .hero-tool-icon {
                width: 36px;
                height: 36px;
                background: var(--landing-panel-bg-strong, rgba(255, 255, 255, 0.08));
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.76));
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
                border-radius: 999px;
                color: var(--landing-text-soft, rgba(245, 245, 243, 0.86));
                background: var(--landing-panel-bg-strong, rgba(255, 255, 255, 0.075));
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.08));
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
                font: 500 13px/1 'Fira Sans', sans-serif;
            }

            .hero-file-size {
                flex-shrink: 0;
                color: var(--landing-text-faint, rgba(245, 245, 243, 0.48));
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
                color: var(--landing-text-subtle, rgba(245, 245, 243, 0.58));
                background: transparent;
                cursor: pointer;
                transition: color 160ms ease, background 160ms ease;
            }

            .hero-file-remove:hover {
                color: var(--landing-text, #fff);
                background: var(--landing-panel-border, rgba(255, 255, 255, 0.10));
            }
            
            .hero-text-left {
                position: absolute;
                bottom: 235px;
                left: 50px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 22px;
                line-height: 1.4;
                color: var(--landing-secondary, #E8E8E8);
                max-width: 260px;
                z-index: 3;
            }
            
            .hero-text-right {
                position: absolute;
                bottom: 235px;
                right: 50px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 22px;
                line-height: 1.4;
                color: var(--landing-secondary, #E8E8E8);
                max-width: 260px;
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
                padding: 12px 24px;
                border-radius: 40px;
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 20px;
                line-height: 24px;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                white-space: nowrap;
                box-shadow: none;
                text-align: center;
                text-decoration: none;
                background: var(--landing-primary, #5768FE);
                color: var(--landing-on-primary, #FFFFFF);
                border: none;
            }
            
            .hero-cta:hover {
                background: #6877ff;
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
                    max-width: 480px;
                    order: 4;
                    border-radius: 24px;
                    padding: 8px;
                    margin: 18px auto 0;
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
                    padding: 40px 20px;
                }

                .hero-title {
                    order: 1;
                }

                .hero-subtitle {
                    order: 2;
                }

                .hero-image-wrapper {
                    order: 3;
                }

                .hero-text-left { order: 5; }
                .hero-cta-row { order: 6; }
                .hero-text-right { order: 7; }
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
    }

    _handleCTA = () => {
        this.navigate('digital-workers');
    };

    _isMode(value) {
        return value === 'quick' || value === 'deep' || value === 'research';
    }

    _setSearchMode(mode) {
        if (!this._isMode(mode)) {
            throw new Error(`Invalid search mode: ${mode}`);
        }
        this._searchMode = mode;
    }

    _handleSearchInput(event) {
        const target = event.target;
        if (!target || typeof target.value !== 'string') {
            return;
        }
        this._searchQuery = target.value;
    }

    _fileErrorMessage(error) {
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

    _handleFilesSelected(event) {
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

    _removeFile(index) {
        if (!Number.isInteger(index) || index < 0 || index >= this._selectedFiles.length) {
            throw new Error('LandingHero._removeFile: index out of range');
        }
        this._selectedFiles = this._selectedFiles.filter((_, itemIndex) => itemIndex !== index);
    }

    _submitSearch(event) {
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

    _renderModeChip(mode) {
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

    _renderSelectedFile(file, index) {
        return html`
            <div class="hero-file-chip" role="listitem">
                <platform-icon file-icon name=${resolveFileIconKey(file.name, file.type)} size="18"></platform-icon>
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

    render() {
        const t = (key) => this.t(key);
        return html`
            <div class="hero-container">
                <h1 class="hero-title">HUMANITEC</h1>
                <p class="hero-subtitle">${t('hero.subtitle')}</p>
                
                    <div class="hero-image-wrapper">
                        <img
                            src="/static/frontend/assets/images/main_img.png"
                            alt=${t('hero.image_alt')}
                            class="hero-image"
                        />
                    </div>

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
            </div>
        `;
    }
}

customElements.define('landing-hero', LandingHero);
