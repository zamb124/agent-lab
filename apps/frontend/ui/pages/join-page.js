/**
 * Join page — приём инвайта по ссылке.
 *
 * Использует `acceptInviteOp` через useOp; перезагрузка пользователя и
 * навигация после успеха выполняются в onSuccess фабрики.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

export class JoinPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex; align-items: center; justify-content: center;
                min-height: 100vh; padding: var(--space-6);
            }
            .card {
                max-width: 460px; padding: var(--space-8);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-2xl);
                text-align: center;
            }
            .card h1 { color: var(--text-primary); margin-bottom: var(--space-4); }
            .card p { color: var(--text-secondary); }
            .btn {
                margin-top: var(--space-4); padding: var(--space-3) var(--space-6);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-lg); cursor: pointer;
                font-size: var(--text-base);
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .err { color: var(--error); margin-top: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this._invite = this.useOp('frontend/invite_accept');
    }

    _shortCode() {
        const u = new URL(window.location.href);
        return u.searchParams.get('c');
    }

    _accept() {
        const code = this._shortCode();
        if (!code) return;
        this._invite.run({ short_code: code });
    }

    render() {
        const codeMissing = !this._shortCode();
        const busy = this._invite.busy;
        const error = this._invite.error;
        const done = !!this._invite.lastResult;

        if (done) {
            return html`
                <div class="card">
                    <h1>${this.t('join_page.title')}</h1>
                    <p>${this.t('join_page.done')}</p>
                </div>
            `;
        }

        const errorMessage = codeMissing
            ? this.t('join_page.no_token_text')
            : error;

        return html`
            <div class="card">
                <h1>${this.t('join_page.title')}</h1>
                <p>${this.t('join_page.text')}</p>
                ${errorMessage ? html`<p class="err">${errorMessage}</p>` : ''}
                <button class="btn" ?disabled=${busy || codeMissing} @click=${() => this._accept()}>
                    ${busy
                        ? this.t('join_page.processing')
                        : this.t('join_page.accept')}
                </button>
            </div>
        `;
    }
}

customElements.define('join-page', JoinPage);
