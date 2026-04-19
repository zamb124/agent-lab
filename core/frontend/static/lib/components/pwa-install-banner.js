/**
 * PWA Install Banner — показ инструкции установки на iOS и кнопки установки
 * на Android/Desktop. Полностью event-driven: PWA state приходит из state.pwa,
 * установка инициируется через dispatch('pwa/install/prompt_requested').
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { PWA_EVENTS } from '../events/effects/pwa.effect.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import './platform-icon.js';

const DISMISS_KEY = 'pwa-banner-dismissed';

function _detectPlatform() {
    const ua = navigator.userAgent;
    if (/iPad|iPhone|iPod/.test(ua) && !window.MSStream) return 'ios';
    if (/android/i.test(ua)) return 'android';
    return 'desktop';
}

function _isIOSSafari() {
    const ua = navigator.userAgent;
    return /Safari/.test(ua) && /iPad|iPhone|iPod/.test(ua) && !/CriOS|FxiOS/.test(ua);
}

function _isInstalled() {
    return window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
}

export class PWAInstallBanner extends PlatformElement {
    static properties = {
        _dismissed: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host { display: block; position: fixed; bottom: 0; left: 0; right: 0; z-index: 9999; pointer-events: none; }
            :host([visible]) .banner { transform: translateY(0); pointer-events: auto; }
            .banner {
                background: rgba(26, 26, 46, 0.98);
                backdrop-filter: blur(20px);
                border-top: 1px solid rgba(87, 104, 254, 0.3);
                padding: 1rem;
                transform: translateY(100%);
                transition: transform 0.3s ease;
            }
            .content { max-width: 600px; margin: 0 auto; display: flex; align-items: center; gap: 1rem; }
            .icon {
                width: 48px; height: 48px;
                background: rgba(87, 104, 254, 0.15);
                border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
            }
            .icon platform-icon { color: #5768fe; }
            .text { flex: 1; }
            .title { font-size: 0.9375rem; font-weight: 600; color: rgba(255, 255, 255, 0.95); margin-bottom: 0.25rem; }
            .description { font-size: 0.8125rem; color: rgba(255, 255, 255, 0.6); line-height: 1.4; }
            .ios-steps { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem; color: rgba(255, 255, 255, 0.7); font-size: 0.75rem; }
            .actions { display: flex; gap: 0.5rem; flex-shrink: 0; }
            @media (max-width: 480px) { .content { flex-direction: column; text-align: center; } .actions { width: 100%; justify-content: center; } }
        `,
    ];

    constructor() {
        super();
        this.platform = _detectPlatform();
        this._dismissed = !!localStorage.getItem(DISMISS_KEY);
        this._pwaSelect = this.select((s) => ({
            installAvailable: s.pwa.installAvailable,
            installed: s.pwa.installed,
        }));
    }

    _shouldShow() {
        if (this._dismissed) return false;
        if (_isInstalled()) return false;
        const pwa = this._pwaSelect.value || { installAvailable: false, installed: false };
        if (pwa.installed) return false;
        if (this.platform === 'ios') return _isIOSSafari();
        return pwa.installAvailable;
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (this._shouldShow()) this.setAttribute('visible', '');
        else this.removeAttribute('visible');
    }

    _install() {
        this.dispatch(PWA_EVENTS.INSTALL_PROMPT_REQUESTED, null);
    }

    _dismiss() {
        this._dismissed = true;
        localStorage.setItem(DISMISS_KEY, 'true');
    }

    render() {
        if (this.platform === 'ios') return this._renderIosBanner();
        return this._renderInstallBanner();
    }

    _renderIosBanner() {
        const t = (k, fallback) => this.t(k) || fallback;
        return html`
            <div class="banner">
                <div class="content">
                    <div class="icon"><platform-icon name="share" size="24"></platform-icon></div>
                    <div class="text">
                        <div class="title">${t('pwa.install_title', 'Add to Home Screen')}</div>
                        <div class="description">${t('pwa.ios_description', 'Tap the share icon and choose "Add to Home Screen".')}</div>
                        <div class="ios-steps">
                            <span>${t('pwa.ios_tap', 'Tap')}</span>
                            <platform-icon name="share" size="20"></platform-icon>
                            <span>${t('pwa.ios_home', 'Add to Home Screen')}</span>
                        </div>
                    </div>
                    <div class="actions">
                        <button class="btn btn-secondary" @click=${this._dismiss}>${t('pwa.later', 'Later')}</button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderInstallBanner() {
        const t = (k, fallback) => this.t(k) || fallback;
        return html`
            <div class="banner">
                <div class="content">
                    <div class="icon"><platform-icon name="cloud" size="24"></platform-icon></div>
                    <div class="text">
                        <div class="title">${t('pwa.install_title', 'Install app')}</div>
                        <div class="description">${t('pwa.install_description', 'Install for quicker access and offline support.')}</div>
                    </div>
                    <div class="actions">
                        <button class="btn btn-secondary" @click=${this._dismiss}>${t('pwa.later', 'Later')}</button>
                        <button class="btn btn-primary" @click=${this._install}>${t('pwa.install', 'Install')}</button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('pwa-install-banner', PWAInstallBanner);
