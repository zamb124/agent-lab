/**
 * Публичная страница скачивания HumanitecAgent (/agent).
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import {
    marketingPageHostStyles,
    marketingHeroStyles,
    marketingFeatureGridStyles,
    marketingDownloadStyles,
} from '@platform/lib/styles/shared/marketing-section.styles.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

const AGENT_DOWNLOAD_BASE = '/frontend/api/agent/download';

/** @typedef {{ href: string, labelKey: string, secondary?: boolean }} AgentDownloadButtonSpec */

export class AgentDownloadPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static styles = [
        PlatformPage.styles,
        marketingPageHostStyles,
        marketingHeroStyles,
        marketingFeatureGridStyles,
        marketingDownloadStyles,
        css`
            .marketing-hero-logo-only .marketing-hero-shot {
                display: none;
            }
        `,
    ];

    constructor() {
        super();
        this._releases = this.useOp('frontend/agent_releases_status');
    }

    connectedCallback() {
        super.connectedCallback();
        queueMicrotask(() => {
            this._syncDocumentMeta();
            this._releases.run();
        });
    }

    _syncDocumentMeta() {
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        applyPublicDocumentMeta({
            title: this.t('meta.agent_download_title'),
            description: this.t('meta.agent_download_description'),
            canonicalUrl: `${origin}/agent`,
            ogImageUrl: `${origin}/static/core/assets/service_logos/humanitec_agent_logo.svg`,
        });
    }

    _pageKey(relativeKey) {
        return `agent_download_page.${relativeKey}`;
    }

    _pt(relativeKey) {
        return this.t(this._pageKey(relativeKey));
    }

    /** @returns {AgentDownloadButtonSpec[]} */
    _primaryDownloadButtons() {
        if (typeof navigator === 'undefined') {
            return [
                { href: `${AGENT_DOWNLOAD_BASE}/macos-arm64`, labelKey: 'download_macos_short' },
                { href: `${AGENT_DOWNLOAD_BASE}/windows`, labelKey: 'download_windows_short' },
                { href: `${AGENT_DOWNLOAD_BASE}/linux-deb`, labelKey: 'download_linux_short' },
            ];
        }
        const userAgent = navigator.userAgent;
        if (userAgent.includes('Mac')) {
            return [{ href: `${AGENT_DOWNLOAD_BASE}/macos-arm64`, labelKey: 'download_macos' }];
        }
        if (userAgent.includes('Win')) {
            return [{ href: `${AGENT_DOWNLOAD_BASE}/windows`, labelKey: 'download_windows' }];
        }
        if (userAgent.includes('Linux')) {
            return [
                { href: `${AGENT_DOWNLOAD_BASE}/linux-deb`, labelKey: 'download_linux_deb' },
                { href: `${AGENT_DOWNLOAD_BASE}/linux-appimage`, labelKey: 'download_linux_appimage', secondary: true },
            ];
        }
        return [
            { href: `${AGENT_DOWNLOAD_BASE}/macos-arm64`, labelKey: 'download_macos_short' },
            { href: `${AGENT_DOWNLOAD_BASE}/windows`, labelKey: 'download_windows_short' },
            { href: `${AGENT_DOWNLOAD_BASE}/linux-deb`, labelKey: 'download_linux_short' },
        ];
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

    _renderOtherPlatforms() {
        const platforms = [
            { href: `${AGENT_DOWNLOAD_BASE}/windows`, labelKey: 'platform_windows' },
            { href: `${AGENT_DOWNLOAD_BASE}/macos-arm64`, labelKey: 'platform_macos_arm64' },
            { href: `${AGENT_DOWNLOAD_BASE}/macos-x64`, labelKey: 'platform_macos_x64' },
            { href: `${AGENT_DOWNLOAD_BASE}/linux-deb`, labelKey: 'platform_linux_deb' },
            { href: `${AGENT_DOWNLOAD_BASE}/linux-rpm`, labelKey: 'platform_linux_rpm' },
            { href: `${AGENT_DOWNLOAD_BASE}/linux-appimage`, labelKey: 'platform_linux_appimage' },
        ];
        return html`
            <details class="marketing-other-platforms">
                <summary>${this._pt('other_platforms')}</summary>
                <ul>
                    ${platforms.map(
                        (platform) => html`
                            <li>
                                <a href=${platform.href}>${this._pt(platform.labelKey)}</a>
                            </li>
                        `,
                    )}
                </ul>
            </details>
        `;
    }

    render() {
        const primaryButtons = this._primaryDownloadButtons();
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                <section class="marketing-hero marketing-hero-logo-only">
                    <div class="marketing-download-logo">
                        <img
                            src="/static/core/assets/service_logos/humanitec_agent_logo.svg"
                            alt=${this._pt('hero_title')}
                            width="48"
                            height="48"
                            loading="eager"
                            decoding="async"
                        />
                    </div>
                    <h1 class="marketing-hero-title">${this._pt('hero_title')}</h1>
                    <p class="marketing-hero-description">${this._pt('hero_description')}</p>
                </section>

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

                <section class="marketing-download" id="download">
                    ${this._renderReleaseBanner()}
                    <div class="marketing-download-actions">
                        ${primaryButtons.map(
                            (buttonSpec) => html`
                                <a
                                    class="marketing-download-link ${buttonSpec.secondary
                                        ? 'marketing-download-link--secondary'
                                        : 'marketing-download-link--primary'}"
                                    href=${buttonSpec.href}
                                >
                                    ${this._pt(buttonSpec.labelKey)}
                                </a>
                            `,
                        )}
                    </div>
                    ${this._renderOtherPlatforms()}
                    <p class="marketing-download-login">
                        ${this._pt('login_prompt')}
                        <a href="/login">${this._pt('login_link')}</a>
                    </p>
                    <p class="marketing-download-footer-note">${this._pt('footer_note')}</p>
                </section>

                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('agent-download-page', AgentDownloadPage);
