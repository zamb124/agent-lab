/**
 * Страница login — public-маршрут /login.
 *
 * Открывает auth-modal через openModal helper; модалка отрисовывается
 * глобальным platform-modal-stack поверх пустой страницы.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/auth-modal.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

export class LoginPage extends PlatformPage {
    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                min-height: 100vh;
                width: 100%;
                background: var(--bg-gradient);
            }
        `,
    ];

    /**
     * Путь для OAuth return_path из ?redirect_uri= (тот же origin, только path+search).
     * @returns {string|null}
     */
    _loginReturnPathFromAddress() {
        if (typeof window === 'undefined') {
            return null;
        }
        const pageUrl = new URL(window.location.href);
        const raw = pageUrl.searchParams.get('redirect_uri');
        if (raw === null || raw === '') {
            return null;
        }
        if (!URL.canParse(raw)) {
            return null;
        }
        const target = new URL(raw);
        if (target.origin !== window.location.origin) {
            return null;
        }
        const path = `${target.pathname}${target.search}`;
        if (!path.startsWith('/')) {
            return null;
        }
        return path;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const returnPath = this._loginReturnPathFromAddress();
        if (returnPath !== null) {
            this.openModal('auth.login', { returnPath });
            return;
        }
        this.openModal('auth.login');
    }

    override render(): TemplateResult {
        return html``;
    }
}

customElements.define('login-page', LoginPage);
