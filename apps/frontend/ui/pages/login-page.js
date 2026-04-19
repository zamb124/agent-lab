/**
 * Login page — public-маршрут /login.
 *
 * Открывает auth-modal через openModal helper; модалка отрисовывается
 * глобальным platform-modal-stack поверх пустой страницы.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/auth-modal.js';

export class LoginPage extends PlatformPage {
    static styles = [
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

    connectedCallback() {
        super.connectedCallback();
        this.openModal('auth.login');
    }

    render() {
        return html``;
    }
}

customElements.define('login-page', LoginPage);
