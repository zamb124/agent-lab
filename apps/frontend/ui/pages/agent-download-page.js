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

const AGENT_LOGO_SRC = '/static/core/assets/service_logos/humanitec_agent_logo.svg';

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
     * @returns {import('../utils/agent-download-platforms.js').AgentPlatformSpec | null}
     */
    _getPrimaryPlatformSpec() {
        if (this._hostOs === 'windows') {
            return getAgentPlatformSpec('windows');
        }
        if (this._hostOs === 'linux') {
            return getAgentPlatformSpec('linux-deb');
        }
        if (this._hostOs === 'macos') {
            if (this._macArchitecture === 'x64') {
                return getAgentPlatformSpec('macos-x64');
            }
            return getAgentPlatformSpec('macos-arm64');
        }
        return null;
    }

    /**
     * @param {import('../utils/agent-download-platforms.js').AgentPlatformId | null} primaryPlatformId
     * @returns {readonly import('../utils/agent-download-platforms.js').AgentPlatformSpec[]}
     */
    _getAlsoAvailablePlatforms(primaryPlatformId) {
        if (!primaryPlatformId) {
            return AGENT_PLATFORM_CATALOG;
        }
        return AGENT_PLATFORM_CATALOG.filter(
            (platformSpec) => platformSpec.platformId !== primaryPlatformId,
        );
    }

    /**
     * @returns {{ versionValue: string, releaseValue: string, releaseReady: boolean }}
     */
    _resolveReleaseStats() {
        const releasePayload = this._releases.lastResult;
        if (!releasePayload || typeof releasePayload !== 'object') {
            if (this._releases.busy) {
                return {
                    versionValue: this._pt('stat_version_pending'),
                    releaseValue: this._pt('stat_release_unavailable'),
                    releaseReady: false,
                };
            }
            return {
                versionValue: this._pt('stat_version_pending'),
                releaseValue: this._pt('release_check_failed'),
                releaseReady: false,
            };
        }
        const ready = releasePayload.ready === true;
        const latestTag = typeof releasePayload.latest_tag === 'string' ? releasePayload.latest_tag : '';
        const detail = typeof releasePayload.detail === 'string' ? releasePayload.detail : '';
        if (ready) {
            return {
                versionValue: latestTag || this._pt('stat_version_pending'),
                releaseValue: this._pt('stat_release_ready'),
                releaseReady: true,
            };
        }
        return {
            versionValue: this._pt('stat_version_pending'),
            releaseValue: detail || this._pt('stat_release_unavailable'),
            releaseReady: false,
        };
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

    /**
     * @param {import('../utils/agent-download-platforms.js').AgentPlatformSpec} platformSpec
     */
    _renderPlatformRowIcon(platformSpec) {
        const iconMaskStyle = `--marketing-download-platform-icon-mask: url('${platformSpec.iconSrc}')`;
        const downloadLabel = this._pt('platform_card_download');
        return html`
            <a
                class="marketing-agent-download-platform-row-link marketing-agent-download-platform-row-link--${platformSpec.iconTone}"
                href=${this._platformDownloadHref(platformSpec.platformId)}
                aria-label=${`${downloadLabel}: ${this._pt(platformSpec.titleKey)}`}
            >
                <span
                    class="marketing-agent-download-platform-row-icon"
                    style=${iconMaskStyle}
                    aria-hidden="true"
                ></span>
            </a>
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

    /**
     * @param {import('../utils/agent-download-platforms.js').AgentPlatformSpec} platformSpec
     */
    _renderInstallButton(platformSpec) {
        const iconMaskStyle = `--marketing-download-platform-icon-mask: url('${platformSpec.iconSrc}')`;
        return html`
            <a
                class="marketing-download-hero-button"
                href=${this._platformDownloadHref(platformSpec.platformId)}
            >
                ${this._pt('install_agent')}
                <span
                    class="marketing-download-hero-button-icon"
                    style=${iconMaskStyle}
                    aria-hidden="true"
                ></span>
            </a>
        `;
    }

    _renderHeroPrimary() {
        const primaryPlatformSpec = this._getPrimaryPlatformSpec();
        if (!primaryPlatformSpec) {
            return html`
                <p class="marketing-download-hero-hint">${this._pt('choose_platform_hint')}</p>
            `;
        }
        return this._renderInstallButton(primaryPlatformSpec);
    }

    _renderHeroStats() {
        const releaseStats = this._resolveReleaseStats();
        return html`
            <dl class="marketing-agent-download-hero-stats">
                <div class="marketing-agent-download-hero-stat">
                    <dt class="marketing-agent-download-hero-stat-label">${this._pt('stat_version_label')}</dt>
                    <dd class="marketing-agent-download-hero-stat-value">${releaseStats.versionValue}</dd>
                </div>
                <div class="marketing-agent-download-hero-stat">
                    <dt class="marketing-agent-download-hero-stat-label">${this._pt('stat_release_label')}</dt>
                    <dd
                        class="marketing-agent-download-hero-stat-value"
                        data-ready=${releaseStats.releaseReady ? 'true' : 'false'}
                    >
                        ${releaseStats.releaseValue}
                    </dd>
                </div>
                <div class="marketing-agent-download-hero-stat">
                    <dt class="marketing-agent-download-hero-stat-label">${this._pt('stat_platforms_label')}</dt>
                    <dd class="marketing-agent-download-hero-stat-value">${AGENT_PLATFORM_CATALOG.length}</dd>
                </div>
            </dl>
        `;
    }

    _renderAlsoAvailablePlatforms() {
        const primaryPlatformSpec = this._getPrimaryPlatformSpec();
        const primaryPlatformId = primaryPlatformSpec ? primaryPlatformSpec.platformId : null;
        const alsoAvailablePlatforms = this._getAlsoAvailablePlatforms(primaryPlatformId);
        if (alsoAvailablePlatforms.length === 0) {
            return html``;
        }
        return html`
            <div class="marketing-agent-download-platform-row">
                <span class="marketing-agent-download-platform-row-label">${this._pt('also_available_on')}</span>
                <div class="marketing-agent-download-platform-row-icons">
                    ${alsoAvailablePlatforms.map((platformSpec) => this._renderPlatformRowIcon(platformSpec))}
                </div>
            </div>
        `;
    }

    _renderReleaseBanner() {
        const releasePayload = this._releases.lastResult;
        if (!releasePayload || typeof releasePayload !== 'object') {
            if (this._releases.busy) {
                return html``;
            }
            return html`
                <div class="marketing-release-banner marketing-release-banner--hero" data-ready="false">
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
            <div class="marketing-release-banner marketing-release-banner--hero" data-ready=${ready ? 'true' : 'false'}>
                ${bannerText}
            </div>
        `;
    }

    _renderHero() {
        return html`
            <section class="marketing-agent-download-hero">
                <div class="marketing-agent-download-hero-grid">
                    <div class="marketing-agent-download-hero-copy">
                        <div class="marketing-agent-download-hero-brand">
                            <img
                                class="marketing-agent-download-hero-logo"
                                src=${AGENT_LOGO_SRC}
                                alt=""
                                width="48"
                                height="48"
                                decoding="async"
                            />
                            <h1 class="marketing-agent-download-hero-title">${this._pt('hero_title')}</h1>
                        </div>
                        <p class="marketing-agent-download-hero-description">${this._pt('hero_description')}</p>
                        ${this._renderHeroStats()}
                        ${this._renderReleaseBanner()}
                        <div class="marketing-download-hero-primary">${this._renderHeroPrimary()}</div>
                        ${this._renderAlsoAvailablePlatforms()}
                    </div>
                    <div class="marketing-agent-download-hero-visual">
                        <div class="marketing-agent-download-hero-shot">
                            <img
                                src=${landHumanitecAgentHeroUrl}
                                alt=${this._pt('hero_visual_alt')}
                                width="1200"
                                height="967"
                                loading="eager"
                                decoding="async"
                            />
                        </div>
                    </div>
                </div>
                <button
                    type="button"
                    class="marketing-agent-download-learn-more"
                    @click=${this._scrollToAllPlatforms}
                >
                    ${this._pt('learn_more')}
                    <platform-icon name="chevron-down" size="16"></platform-icon>
                </button>
            </section>
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

    render() {
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                ${this._renderHero()}

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
