/**
 * Страница join — приём инвайта по ссылке.
 *
 * Без сессии показывает выбор провайдера OAuth с return_path на текущий URL
 * (включая ?c=). После входа пользователь снова на этой странице и может
 * принять приглашение через `frontend/invite_accept`.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-user-chip.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export class JoinPage extends PlatformPage {
    static override properties: PropertyDeclarations = {
        _oauthLoading: { state: true },
        _oauthError: { state: true },
    }
    declare _oauthLoading: boolean;
    declare _oauthError: string;
;

    static override styles: CSSResultGroup = [
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
            .providers { display: flex; flex-direction: column; gap: var(--space-3); margin-top: var(--space-6); }
            .provider-button {
                display: flex; align-items: center; justify-content: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-bg-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-base); color: var(--text-primary);
                cursor: pointer; transition: var(--motion-transition-interactive);
            }
            .provider-button:hover { background: var(--glass-bg-medium); transform: translateY(-1px); }
            .provider-button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
            .checking { display: flex; flex-direction: column; align-items: center; gap: var(--space-4); }
            .invite-preview {
                text-align: left;
                margin-bottom: var(--space-6);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .invite-preview p { margin: 0 0 var(--space-2); color: var(--text-primary); }
            .invite-preview p:last-child { margin-bottom: 0; }
            .preview-label { color: var(--text-secondary); font-size: var(--text-sm); display: block; margin-bottom: var(--space-1); }
            .logged-in {
                text-align: left;
                margin: var(--space-6) 0;
                display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this._invite = this.useOp('frontend/invite_accept');
        this._preview = this.useOp('frontend/invite_preview');
        this._authStatus = this.select((s) => s.auth.status);
        this._authUser = this.select((s) => s.auth.user);
        this._oauthLoading = false;
        this._oauthError = '';
        this._previewRanFor = null;
        this.useEvent('auth/oauth/failed', (event) => {
            this._oauthLoading = false;
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            const message = payload === null ? undefined : payload.message;
            const msg = typeof message === 'string' ? message : '';
            this._oauthError = msg.length > 0 ? msg : this.t('join_page.oauth_failed');
        });
    }
    private _invite: OpController;
    private _preview: OpController;
    private _authStatus: SelectController<any>;
    private _authUser: SelectController<any>;
    private _previewRanFor: any;


    override connectedCallback(): void {
        super.connectedCallback();
        this._maybeLoadPreview();
    }

    _shortCode() {
        const u = new URL(window.location.href);
        return u.searchParams.get('c');
    }

    _maybeLoadPreview() {
        const code = this._shortCode();
        if (!code) return;
        if (this._previewRanFor === code) return;
        this._previewRanFor = code;
        this._preview.run({ short_code: code });
    }

    _inviteReturnPath() {
        if (typeof window === 'undefined') return '';
        return `${window.location.pathname}${window.location.search}`;
    }

    _accept() {
        const code = this._shortCode();
        if (!code) return;
        this._invite.run({ short_code: code });
    }

    _startProvider(provider: string) {
        if (this._oauthLoading) return;
        this._oauthLoading = true;
        this._oauthError = '';
        this.startOAuth(provider, { returnPath: this._inviteReturnPath() });
    }

    _renderInvitePreview() {
        const code = this._shortCode();
        if (!code) return html``;

        const busy = this._preview.busy;
        const err = this._preview.error;
        const res = this._preview.lastResult;

        if (busy && !res) {
            return html`
                <platform-empty-state class="checking" loading></platform-empty-state>
            `;
        }
        if (err) {
            return html`<p class="err">${err}</p>`;
        }
        if (!res) {
            return html``;
        }
        const preview = isPlainRecord(res) ? res : null;
        if (preview === null) {
            throw new Error('join_page: preview response shape');
        }
        const companyName = preview.company_name;
        const role = preview.role;
        const invitedByName = preview.invited_by_name;
        const invitedByUserId = preview.invited_by_user_id;
        if (
            typeof companyName !== 'string'
            || typeof role !== 'string'
            || typeof invitedByName !== 'string'
            || typeof invitedByUserId !== 'string'
        ) {
            throw new Error('join_page: preview response shape');
        }
        return html`
            <div class="invite-preview">
                <p>
                    <span class="preview-label">${this.t('join_page.preview_company')}</span>
                    ${companyName}
                </p>
                <p>
                    <span class="preview-label">${this.t('join_page.preview_role')}</span>
                    ${role}
                </p>
                <p>
                    <span class="preview-label">${this.t('join_page.preview_inviter')}</span>
                    ${invitedByName}
                </p>
            </div>
        `;
    }

    _renderLoggedInUser() {
        const authStatus = this._authStatus.value;
        if (authStatus !== 'authenticated') return html``;
        const user = this._authUser.value;
        if (!user || typeof user.user_id !== 'string' || user.user_id.length === 0) {
            return html``;
        }
        return html`
            <div class="logged-in">
                <span class="preview-label">${this.t('join_page.logged_in_as')}</span>
                <platform-user-chip .userId=${user.user_id}></platform-user-chip>
            </div>
        `;
    }

    override render(): TemplateResult {
        const authStatus = this._authStatus.value;
        const codeMissing = !this._shortCode();
        const busy = this._invite.busy;
        const error = this._invite.error;
        const done = !!this._invite.lastResult;

        if (authStatus === 'unknown' || authStatus === 'validating') {
            return html`
                <div class="card">
                    ${this._renderInvitePreview()}
                    <platform-empty-state class="checking" loading title=${this.t('join_page.session_checking')}></platform-empty-state>
                </div>
            `;
        }

        if (authStatus === 'unauthenticated' || authStatus === 'error') {
            return html`
                <div class="card">
                    ${this._renderInvitePreview()}
                    <h1>${this.t('join_page.needs_auth_title')}</h1>
                    <p>${this.t('join_page.needs_auth_subtitle')}</p>
                    ${this._oauthError ? html`<p class="err">${this._oauthError}</p>` : ''}
                    <div class="providers">
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('yandex')}>
                            <platform-icon name="yandex" size="24" colored></platform-icon>
                            <span>${this.t('join_page.login_yandex')}</span>
                        </button>
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('google')}>
                            <platform-icon name="google" size="24" colored></platform-icon>
                            <span>${this.t('join_page.login_google')}</span>
                        </button>
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('github')}>
                            <platform-icon name="github" size="24"></platform-icon>
                            <span>${this.t('join_page.login_github')}</span>
                        </button>
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('apple')}>
                            <platform-icon name="apple" size="24"></platform-icon>
                            <span>${this.t('join_page.login_apple')}</span>
                        </button>
                    </div>
                </div>
            `;
        }

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
                ${this._renderInvitePreview()}
                ${this._renderLoggedInUser()}
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
