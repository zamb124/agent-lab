/**
 * sync-call-join-page — вход в звонок по ссылке-приглашению.
 *
 * Без сессии: имя гостя и POST/WS join с `body.guest_name`.
 * С сессией: join от имени `state.auth.user` без поля имени (тот же op_calls_join_accept).
 * После accept — модалка `sync.call_overlay` (гостевые токены или обычный sync/call_token внутри оверлея).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';

export class SyncCallJoinPage extends PlatformPage {
    static i18nNamespace = 'sync';

    static properties = {
        linkToken: { type: String },
        _guestName: { state: true },
        _alignCompanySkipped: { state: true },
    };

    static styles = css`
        :host {
            display: flex;
            flex: 1;
            min-height: 0;
            align-items: center;
            justify-content: center;
            padding: var(--space-6);
            box-sizing: border-box;
        }
        .card {
            width: 100%;
            max-width: 420px;
            padding: var(--space-6);
            box-sizing: border-box;
        }
        .card-inner {
            display: flex;
            flex-direction: column;
            gap: var(--space-4);
        }
        h2 {
            margin: 0;
            font-size: var(--text-xl);
            font-weight: 600;
            color: var(--text-primary);
            line-height: 1.3;
        }
        .meta {
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
            font-size: var(--text-sm);
            color: var(--text-secondary);
        }
        .organizer-row {
            display: flex;
            align-items: center;
            gap: var(--space-3);
        }
        .organizer-row img {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
            border: 1px solid var(--glass-border-subtle);
        }
        .field-label {
            display: block;
            font-size: var(--text-sm);
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: var(--space-2);
        }
        .actions {
            display: flex;
            flex-direction: column;
            gap: var(--space-3);
            margin-top: var(--space-1);
        }
        .error-text {
            margin: 0;
            font-size: var(--text-sm);
            color: var(--error);
            line-height: 1.4;
        }
        .load-panel {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: var(--space-4);
            min-height: 120px;
        }
        .load-panel p {
            margin: 0;
            font-size: var(--text-sm);
            color: var(--text-secondary);
        }
        .divider {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin: var(--space-2) 0;
        }
        .divider::before,
        .divider::after {
            content: '';
            flex: 1;
            height: 1px;
            background: var(--glass-border-subtle);
        }
    `;

    constructor() {
        super();
        this.linkToken = '';
        this._guestName = '';
        this._alignCompanySkipped = false;
        this._alignCompanyDispatched = false;
        this._alignTimerId = null;
        this._infoOp = this.useOp('sync/call_join_info');
        this._acceptOp = this.useOp('sync/call_join_accept');
        this._authSel = this.select((s) => s.auth);
    }

    disconnectedCallback() {
        if (this._alignTimerId !== null) {
            window.clearTimeout(this._alignTimerId);
            this._alignTimerId = null;
        }
        super.disconnectedCallback?.();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('linkToken')) {
            this._alignCompanyDispatched = false;
            this._alignCompanySkipped = false;
            if (this._alignTimerId !== null) {
                window.clearTimeout(this._alignTimerId);
                this._alignTimerId = null;
            }
        }
        if (changed.has('linkToken') && this.linkToken) {
            void this._infoOp.run({ link_token: this.linkToken });
        }
        this._scheduleAlignCompany();
    }

    _matchedInfo() {
        const r = this._infoOp.lastResult;
        if (r === null) return null;
        if (typeof r.link_token !== 'string' || r.link_token !== this.linkToken) return null;
        return r;
    }

    _targetCompanyId(info) {
        if (typeof window !== 'undefined') {
            const raw = new URLSearchParams(window.location.search).get('company_id');
            if (typeof raw === 'string' && raw.trim() !== '') {
                return raw.trim();
            }
        }
        if (info !== null && typeof info.company_id === 'string' && info.company_id !== '') {
            return info.company_id;
        }
        return '';
    }

    _companyAlignLoading(info, auth) {
        if (!this._isAuthenticated(auth)) return false;
        if (this._alignCompanySkipped) return false;
        const target = this._targetCompanyId(info);
        if (target === '') return false;
        return auth.activeCompanyId !== target;
    }

    _scheduleAlignCompany() {
        const info = this._matchedInfo();
        if (info === null) return;
        const auth = this._authSel.value;
        if (!this._isAuthenticated(auth)) return;
        const target = this._targetCompanyId(info);
        if (target === '') return;
        if (auth.activeCompanyId === target) {
            if (this._alignTimerId !== null) {
                window.clearTimeout(this._alignTimerId);
                this._alignTimerId = null;
            }
            return;
        }
        if (this._alignCompanySkipped) return;
        if (this._alignCompanyDispatched) return;
        this._alignCompanyDispatched = true;
        this.switchCompany(target);
        this._alignTimerId = window.setTimeout(() => {
            this._alignTimerId = null;
            this._alignCompanySkipped = true;
            this.requestUpdate();
        }, 8000);
    }

    _authSessionReady(auth) {
        if (auth === null || auth === undefined) return false;
        const st = auth.status;
        return st === 'authenticated' || st === 'unauthenticated' || st === 'error';
    }

    _isAuthenticated(auth) {
        if (auth === null || auth === undefined) return false;
        if (auth.status !== 'authenticated') return false;
        const u = auth.user;
        if (u === null || u === undefined) return false;
        return typeof u.user_id === 'string' && u.user_id !== '';
    }

    _userDisplayName(user) {
        if (user === null || user === undefined) return '';
        if (typeof user.name === 'string' && user.name.trim() !== '') {
            return user.name.trim();
        }
        if (typeof user.email === 'string' && user.email.trim() !== '') {
            return user.email.trim();
        }
        return '';
    }

    _openOverlayFromAccepted(accepted) {
        if (typeof accepted.call_id !== 'string' || accepted.call_id === '') return;
        const callType = typeof accepted.call_type === 'string' && accepted.call_type !== ''
            ? accepted.call_type
            : 'video';
        const livekitToken = typeof accepted.livekit_token === 'string' ? accepted.livekit_token : '';
        const livekitUrl = typeof accepted.livekit_url === 'string' ? accepted.livekit_url : '';
        const participantNames = accepted.participant_names !== null
            && accepted.participant_names !== undefined
            && typeof accepted.participant_names === 'object'
            ? accepted.participant_names
            : {};
        const participantIdentity = typeof accepted.participant_identity === 'string'
            ? accepted.participant_identity
            : '';
        this.openModal('sync.call_overlay', {
            callId: accepted.call_id,
            callType,
            channelId: '',
            livekitToken,
            livekitUrl,
            participantNames,
            participantIdentity,
        });
    }

    async _onJoinRegistered() {
        await this._acceptOp.run({
            link_token: this.linkToken,
        });
        const accepted = this._acceptOp.lastResult;
        if (accepted === null) return;
        this._openOverlayFromAccepted(accepted);
    }

    async _onJoinGuest() {
        const trimmed = this._guestName.trim();
        if (trimmed.length === 0) return;
        await this._acceptOp.run({
            link_token: this.linkToken,
            body: { guest_name: trimmed },
        });
        const accepted = this._acceptOp.lastResult;
        if (accepted === null) return;
        this._openOverlayFromAccepted(accepted);
    }

    _onOpenLoginModal() {
        const path = typeof window !== 'undefined'
            ? window.location.pathname + window.location.search
            : '/sync';
        this.openModal('auth.login', { returnPath: path });
    }

    _retryInfo() {
        if (this.linkToken) {
            void this._infoOp.run({ link_token: this.linkToken });
        }
    }

    _heading(info) {
        if (info !== null && typeof info.channel_name === 'string' && info.channel_name !== '') {
            return info.channel_name;
        }
        return this.t('call_join.title');
    }

    _renderGuestBlock() {
        return html`
            <platform-field
                type="string"
                mode="edit"
                .label=${this.t('call_join.label_guest_name')}
                .value=${this._guestName}
                .placeholder=${this.t('call_join.guest_name_placeholder')}
                ?disabled=${this._acceptOp.busy}
                @change=${(e) => {
                    this._guestName = e.detail.value;
                }}
            ></platform-field>
            <div class="actions">
                <platform-button
                    variant="primary"
                    ?loading=${this._acceptOp.busy}
                    ?disabled=${this._guestName.trim().length === 0 || this._acceptOp.busy}
                    @click=${() => void this._onJoinGuest()}
                >
                    ${this.t('call_join.guest_button')}
                </platform-button>
            </div>
        `;
    }

    _renderInfoBody(info, auth) {
        const organizer = typeof info.creator_display_name === 'string' ? info.creator_display_name : '';
        const avatar =
            typeof info.creator_avatar_url === 'string' && info.creator_avatar_url !== ''
                ? info.creator_avatar_url
                : '';
        const hasOrganizer = organizer !== '';
        const authed = this._isAuthenticated(auth);
        const user = authed ? auth.user : null;
        const displayName = this._userDisplayName(user);
        const registeredJoinLabel = displayName !== ''
            ? this.t('call_join.join_as', { name: displayName })
            : this.t('call_join.action_join');

        return html`
            <div class="meta">
                ${hasOrganizer
                    ? html`
                          <div class="organizer-row">
                              ${avatar !== ''
                                  ? html`<img src=${avatar} alt="" width="40" height="40" />`
                                  : ''}
                              <span>${this.t('call_join.organizer')}: ${organizer}</span>
                          </div>
                      `
                    : ''}
            </div>
            ${this._acceptOp.error !== null
                ? html`<p class="error-text">${this.t('call_join.err_join')}</p>`
                : ''}
            ${authed
                ? html`
                      <div class="actions">
                          <platform-button
                              variant="primary"
                              ?loading=${this._acceptOp.busy}
                              ?disabled=${this._acceptOp.busy}
                              @click=${() => void this._onJoinRegistered()}
                          >
                              ${registeredJoinLabel}
                          </platform-button>
                      </div>
                      <div class="divider">${this.t('call_join.divider_or')}</div>
                      ${this._renderGuestBlock()}
                  `
                : html`
                      <div class="actions">
                          <platform-button
                              variant="secondary"
                              ?disabled=${this._acceptOp.busy}
                              @click=${() => this._onOpenLoginModal()}
                          >
                              ${this.t('call_join.login_account')}
                          </platform-button>
                      </div>
                      <div class="divider">${this.t('call_join.divider_or')}</div>
                      ${this._renderGuestBlock()}
                  `}
        `;
    }

    render() {
        const info = this._matchedInfo();
        const infoFailed = this._infoOp.error !== null && info === null && !this._infoOp.busy;
        const infoLoading = this._infoOp.busy && info === null;
        const auth = this._authSel.value;
        const authLoading = info !== null && !this._authSessionReady(auth);

        if (infoLoading) {
            return html`
                <glass-card class="card">
                    <div class="load-panel" role="status" aria-live="polite">
                        <glass-spinner size="lg"></glass-spinner>
                        <p>${this.t('call_join.loading')}</p>
                    </div>
                </glass-card>
            `;
        }

        if (infoFailed) {
            return html`
                <glass-card class="card">
                    <div class="card-inner">
                        <h2>${this.t('call_join.title')}</h2>
                        <p class="error-text">${this.t('call_join.err_load_failed')}</p>
                        <platform-button variant="secondary" @click=${() => this._retryInfo()}>
                            ${this.t('call_join.retry')}
                        </platform-button>
                    </div>
                </glass-card>
            `;
        }

        if (info === null) {
            return html`
                <glass-card class="card">
                    <div class="load-panel" role="status">
                        <glass-spinner size="lg"></glass-spinner>
                    </div>
                </glass-card>
            `;
        }

        if (authLoading) {
            return html`
                <glass-card class="card">
                    <div class="load-panel" role="status" aria-live="polite">
                        <glass-spinner size="lg"></glass-spinner>
                        <p>${this.t('call_join.loading')}</p>
                    </div>
                </glass-card>
            `;
        }

        if (this._companyAlignLoading(info, auth)) {
            return html`
                <glass-card class="card">
                    <div class="load-panel" role="status" aria-live="polite">
                        <glass-spinner size="lg"></glass-spinner>
                        <p>${this.t('call_join.aligning_company')}</p>
                    </div>
                </glass-card>
            `;
        }

        const title = this._heading(info);
        return html`
            <glass-card class="card">
                <div class="card-inner">
                    <h2>${title}</h2>
                    ${this._renderInfoBody(info, auth)}
                </div>
            </glass-card>
        `;
    }
}

customElements.define('sync-call-join-page', SyncCallJoinPage);
