/**
 * Публичная страница скачивания HumanitecAgent (/agent).
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingAgentDownloadPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import '@platform/lib/components/platform-icon.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import { landHumanitecAgentHeroUrl } from '../utils/land-product-images.js';
import {
    AGENT_DOWNLOAD_BASE,
    AGENT_PLATFORM_CATALOG,
    detectAgentHostOs,
    detectAgentMacArchitecture,
    getAgentPlatformSpec,
} from '../utils/agent-download-platforms.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class AgentDownloadPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static styles = [PlatformPage.styles, marketingAgentDownloadPageStyles];

    constructor() {
        super();
        this._releases = this.useOp('frontend/agent_releases_status');
        this._hostOs = detectAgentHostOs();
        this._macArchitecture = 'unknown';
    }

    connectedCallback() {
        super.connectedCallback();
        queueMicrotask(() => {
            this._syncDocumentMeta();
            this._releases.run();
            void this._resolveMacArchitecture();
        });
    }

    async _resolveMacArchitecture() {
        const macArchitecture = await detectAgentMacArchitecture();
        if (this._macArchitecture === macArchitecture) {
            return;
        }
        this._macArchitecture = macArchitecture;
        this.requestUpdate();
    }

    _syncDocumentMeta() {
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        applyPublicDocumentMeta({
            title: this.t('meta.agent_download_title'),
            description: this.t('meta.agent_download_description'),
            canonicalUrl: `${origin}/agent`,
            ogImageUrl: `${origin}${landHumanitecAgentHeroUrl}`,
        });
    }

    _pageKey(relativeKey) {
        return `agent_download_page.${relativeKey}`;
    }

    _pt(relativeKey) {
        return this.t(this._pageKey(relativeKey));
    }

    _platformDownloadHref(platformId) {
        return `${AGENT_DOWNLOAD_BASE}/${platformId}`;
    }

    /**
     * @param {import('../utils/agent-download-platforms.js').AgentPlatformSpec} platformSpec
     */
    _renderPlatformIcon(platformSpec) {
        const iconMaskStyle = `--marketing-download-platform-icon-mask: url('${platformSpec.iconSrc}')`;
        return html`
            <span
                class="marketing-download-platform-card-icon-wrap marketing-download-platform-card-icon-wrap--${platformSpec.iconTone}"
            >
                <span
                    class="marketing-download-platform-card-icon"
                    style=${iconMaskStyle}
                    aria-hidden="true"
                ></span>
            </span>
        `;
    }

    _scrollToAllPlatforms() {
        const section = this.renderRoot.querySelector('#all-platforms');
        if (!section) {
            throw new Error('agent_download_page: #all-platforms section is missing');
        }
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /**
     * @param {import('../utils/agent-download-platforms.js').AgentPlatformSpec} platformSpec
     * @param {{ hero?: boolean, recommended?: boolean }} [options]
     */
    _renderPlatformCard(platformSpec, options = {}) {
        const hero = options.hero === true;
        const recommended = options.recommended === true;
        const cardClasses = [
            'marketing-download-platform-card',
            'glass-medium',
            'glass-interactive',
            hero ? 'marketing-download-platform-card--hero' : '',
            recommended ? 'marketing-download-platform-card--recommended' : '',
        ]
            .filter(Boolean)
            .join(' ');
        const downloadLabel = this._pt('platform_card_download');
        return html`
            <a
                class=${cardClasses}
                href=${this._platformDownloadHref(platformSpec.platformId)}
                aria-label=${`${downloadLabel}: ${this._pt(platformSpec.titleKey)}`}
            >
                ${recommended
                    ? html`
                          <span class="marketing-download-platform-card-badge">
                              ${this._pt('platform_card_recommended')}
                          </span>
                      `
                    : ''}
                ${this._renderPlatformIcon(platformSpec)}
                <span class="marketing-download-platform-card-title">${this._pt(platformSpec.titleKey)}</span>
                <span class="marketing-download-platform-card-subtitle">
                    ${this._pt(platformSpec.subtitleKey)}
                </span>
                <span class="marketing-download-platform-card-action">
                    ${downloadLabel}
                    <platform-icon name="chevron-right" size="16"></platform-icon>
                </span>
            </a>
        `;
    }

    _renderHeroPrimary() {
        if (this._hostOs === 'macos') {
            const arm64Spec = getAgentPlatformSpec('macos-arm64');
            const x64Spec = getAgentPlatformSpec('macos-x64');
            const recommendArm64 = this._macArchitecture === 'arm64';
            return html`
                <div class="marketing-download-hero-cards">
                    ${this._renderPlatformCard(arm64Spec, { hero: true, recommended: recommendArm64 })}
                    ${this._renderPlatformCard(x64Spec, { hero: true })}
                </div>
            `;
        }
        if (this._hostOs === 'windows') {
            const windowsSpec = getAgentPlatformSpec('windows');
            return html`
                <a
                    class="marketing-download-hero-button"
                    href=${this._platformDownloadHref(windowsSpec.platformId)}
                >
                    <span
                        class="marketing-download-hero-button-icon"
                        style="--marketing-download-platform-icon-mask: url('${windowsSpec.iconSrc}')"
                        aria-hidden="true"
                    ></span>
                    ${this._pt('download_windows')}
                </a>
            `;
        }
        if (this._hostOs === 'linux') {
            const debSpec = getAgentPlatformSpec('linux-deb');
            return this._renderPlatformCard(debSpec, { hero: true });
        }
        return html`
            <p class="marketing-download-hero-hint">${this._pt('choose_platform_hint')}</p>
        `;
    }

    _renderAllPlatformCards() {
        return html`
            <section class="marketing-download-all-platforms" id="all-platforms">
                <h2 class="marketing-download-all-platforms-title">${this._pt('all_platforms_title')}</h2>
                <div class="marketing-download-all-platforms-grid">
                    ${AGENT_PLATFORM_CATALOG.map((platformSpec) => this._renderPlatformCard(platformSpec))}
                </div>
            </section>
        `;
    }

    _renderReleaseBanner() {
        const releasePayload = this._releases.lastResult;
        if (!releasePayload || typeof releasePayload !== 'object') {
            if (this._releases.busy) {
                return html``;
            }
            return html`
                <div class="marketing-release-banner" data-ready="false">
                    ${this._pt('release_check_failed')}
                </div>
            `;
        }
        const ready = releasePayload.ready === true;
        const latestTag = typeof releasePayload.latest_tag === 'string' ? releasePayload.latest_tag : '';
        const detail = typeof releasePayload.detail === 'string' ? releasePayload.detail : '';
        const bannerText = ready
            ? `${this._pt('release_ready')}${latestTag ? ` ${latestTag}` : ''}`
            : detail || this._pt('release_not_ready');
        return html`
            <div class="marketing-release-banner" data-ready=${ready ? 'true' : 'false'}>
                ${bannerText}
            </div>
        `;
    }

    render() {
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                <section class="marketing-hero">
                    <h1 class="marketing-hero-title">${this._pt('hero_title')}</h1>
                    <div class="marketing-hero-shot">
                        <img
                            src=${landHumanitecAgentHeroUrl}
                            alt=${this._pt('hero_visual_alt')}
                            width="1200"
                            height="967"
                            loading="eager"
                            decoding="async"
                        />
                    </div>
                    <p class="marketing-hero-description">${this._pt('hero_description')}</p>
                    ${this._renderReleaseBanner()}
                    <div class="marketing-download-hero-primary">${this._renderHeroPrimary()}</div>
                    <button type="button" class="marketing-download-scroll-trigger" @click=${this._scrollToAllPlatforms}>
                        ${this._pt('other_platforms')}
                        <platform-icon name="chevron-down" size="16"></platform-icon>
                    </button>
                </section>

                ${this._renderAllPlatformCards()}

                <section class="marketing-features">
                    <div class="marketing-features-grid">
                        ${[1, 2, 3, 4].map(
                            (index) => html`
                                <div class="marketing-feature-card glass-medium glass-interactive">
                                    <h3 class="marketing-feature-title">${this._pt(`f${index}_title`)}</h3>
                                    <p class="marketing-feature-description">${this._pt(`f${index}_desc`)}</p>
                                </div>
                            `,
                        )}
                    </div>
                </section>

                <div class="marketing-download-postscript">
                    <p class="marketing-download-login">
                        ${this._pt('login_prompt')}
                        <a href="/login">${this._pt('login_link')}</a>
                    </p>
                    <p class="marketing-download-footer-note">${this._pt('footer_note')}</p>
                </div>

                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('agent-download-page', AgentDownloadPage);
