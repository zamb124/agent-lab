import { LitElement, html, css } from 'lit';
import { i18n } from '../../services/i18n/i18n.service.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import './platform-icon.js';

/**
 * PWA Install Banner - показывает инструкцию установки на iOS
 * и кнопку установки на Android/Desktop
 */
export class PWAInstallBanner extends LitElement {
    static properties = {
        visible: { type: Boolean, reflect: true },
        platform: { type: String },
        _dismissed: { type: Boolean, state: true }
    };

    static styles = [buttonStyles, css`
        :host {
            display: block;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            z-index: 9999;
            pointer-events: none;
        }

        :host([visible]) .banner {
            transform: translateY(0);
            pointer-events: auto;
        }

        .banner {
            background: rgba(26, 26, 46, 0.98);
            backdrop-filter: blur(20px);
            border-top: 1px solid rgba(87, 104, 254, 0.3);
            padding: 1rem;
            transform: translateY(100%);
            transition: transform 0.3s ease;
        }

        .content {
            max-width: 600px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .icon {
            width: 48px;
            height: 48px;
            background: rgba(87, 104, 254, 0.15);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .icon platform-icon {
            color: #5768fe;
        }

        .text {
            flex: 1;
        }

        .title {
            font-size: 0.9375rem;
            font-weight: 600;
            color: rgba(255, 255, 255, 0.95);
            margin-bottom: 0.25rem;
        }

        .description {
            font-size: 0.8125rem;
            color: rgba(255, 255, 255, 0.6);
            line-height: 1.4;
        }

        .ios-steps {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 0.5rem;
            color: rgba(255, 255, 255, 0.7);
            font-size: 0.75rem;
        }

        .ios-steps platform-icon {
            vertical-align: middle;
        }

        .actions {
            display: flex;
            gap: 0.5rem;
            flex-shrink: 0;
        }


        @media (max-width: 480px) {
            .content {
                flex-direction: column;
                text-align: center;
            }

            .actions {
                width: 100%;
                justify-content: center;
            }
        }
    `];

    constructor() {
        super();
        this.visible = false;
        this.platform = this._detectPlatform();
        this._dismissed = false;
        this._deferredPrompt = null;

        this._setupListeners();
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = i18n.subscribe(() => this.requestUpdate());
        setTimeout(() => this._checkAndShow(), 2000);
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    _detectPlatform() {
        const ua = navigator.userAgent;
        if (/iPad|iPhone|iPod/.test(ua) && !window.MSStream) return 'ios';
        if (/android/i.test(ua)) return 'android';
        return 'desktop';
    }

    _setupListeners() {
        // Слушаем событие beforeinstallprompt для Android/Desktop
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this._deferredPrompt = e;
            this._checkAndShow();
        });

        // Слушаем PWA события от нашего сервиса
        document.addEventListener('pwa-install-available', () => {
            this._checkAndShow();
        });

        document.addEventListener('pwa-installed', () => {
            this.visible = false;
        });
    }

    _checkAndShow() {
        if (this._dismissed) return;
        if (this._isInstalled()) return;
        if (localStorage.getItem('pwa-banner-dismissed')) return;

        // На iOS показываем если в Safari и не установлено
        if (this.platform === 'ios' && this._isIOSSafari()) {
            this.visible = true;
            return;
        }

        // На Android/Desktop показываем если есть deferredPrompt
        if (this._deferredPrompt) {
            this.visible = true;
        }
    }

    _isInstalled() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    }

    _isIOSSafari() {
        const ua = navigator.userAgent;
        return /Safari/.test(ua) && /iPad|iPhone|iPod/.test(ua) && !/CriOS|FxiOS/.test(ua);
    }

    async _install() {
        if (this._deferredPrompt) {
            this._deferredPrompt.prompt();
            const { outcome } = await this._deferredPrompt.userChoice;
            this._deferredPrompt = null;
            
            if (outcome === 'accepted') {
                this.visible = false;
            }
        }
    }

    _dismiss() {
        this.visible = false;
        this._dismissed = true;
        localStorage.setItem('pwa-banner-dismissed', 'true');
    }

    render() {
        if (this.platform === 'ios') {
            return this._renderIOSBanner();
        }
        return this._renderInstallBanner();
    }

    _renderIOSBanner() {
        const t = (key) => i18n.t(key, {}, 'shell');
        return html`
            <div class="banner">
                <div class="content">
                    <div class="icon">
                        <platform-icon name="share" size="24"></platform-icon>
                    </div>
                    <div class="text">
                        <div class="title">${t('pwa.install_title')}</div>
                        <div class="description">${t('pwa.ios_description')}</div>
                        <div class="ios-steps">
                            <span>${t('pwa.ios_tap')}</span>
                            <platform-icon name="share" size="20"></platform-icon>
                            <span>${t('pwa.ios_home')}</span>
                        </div>
                    </div>
                    <div class="actions">
                        <button class="btn btn-secondary" @click=${this._dismiss}>${t('pwa.later')}</button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderInstallBanner() {
        const t = (key) => i18n.t(key, {}, 'shell');
        return html`
            <div class="banner">
                <div class="content">
                    <div class="icon">
                        <platform-icon name="import" size="24"></platform-icon>
                    </div>
                    <div class="text">
                        <div class="title">${t('pwa.install_title')}</div>
                        <div class="description">${t('pwa.install_description')}</div>
                    </div>
                    <div class="actions">
                        <button class="btn btn-secondary" @click=${this._dismiss}>${t('pwa.later')}</button>
                        <button class="btn btn-primary" @click=${this._install}>${t('pwa.install')}</button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('pwa-install-banner', PWAInstallBanner);
