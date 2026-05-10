/**
 * Публичная страница поддержки: email + форма, отправка через mailto (без backend).
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import { isValidEmail } from '@platform/lib/utils/validators.js';

const SUPPORT_EMAIL = 'zambas124@gmail.com';
const MAX_SUBJECT = 200;
const MAX_MESSAGE = 12000;
const MAX_MAILTO_HREF = 1950;

export class SupportPage extends PlatformPage {
    static i18nNamespace = 'frontend';

    static properties = {
        _replyEmail: { state: true },
        _subject: { state: true },
        _message: { state: true },
        _status: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                min-height: 100%;
                box-sizing: border-box;
                max-width: 44rem;
                margin: 0 auto;
                padding: var(--space-10) var(--space-6) var(--space-16);
                color: var(--text-primary);
                background: var(--bg-gradient);
            }
            .back-row {
                margin-bottom: var(--space-6);
                display: flex;
                justify-content: flex-start;
            }
            .page-head {
                margin-bottom: var(--space-10);
                text-align: center;
            }
            h1 {
                font-size: clamp(var(--text-2xl), 4vw, var(--text-3xl));
                font-weight: 600;
                margin: 0 0 var(--space-3);
                letter-spacing: -0.02em;
            }
            .lede {
                color: var(--text-secondary);
                margin: 0;
                line-height: 1.6;
                font-size: var(--text-base);
                max-width: 36rem;
                margin-left: auto;
                margin-right: auto;
            }
            .stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-6);
            }
            .section-title {
                font-size: var(--text-sm);
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
                margin: 0 0 var(--space-3);
            }
            .email-row {
                display: flex;
                align-items: flex-start;
                gap: var(--space-4);
            }
            .email-row .icon-wrap {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                border-radius: var(--radius-md);
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(87, 104, 254, 0.12);
                border: 1px solid rgba(87, 104, 254, 0.25);
                color: var(--accent);
            }
            .email-row a {
                color: var(--accent);
                font-size: var(--text-lg);
                font-weight: 500;
                word-break: break-all;
            }
            .email-row a:hover {
                text-decoration: underline;
            }
            .field {
                margin-bottom: var(--space-4);
            }
            .field:last-of-type {
                margin-bottom: 0;
            }
            .field label {
                display: block;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-1);
            }
            .req {
                color: var(--warning, #c9a655);
            }
            .actions {
                margin-top: var(--space-5);
            }
            .status {
                font-size: var(--text-sm);
                margin-top: var(--space-3);
                min-height: 1.25em;
            }
            .status.is-error {
                color: var(--error);
            }
            .status.is-ok {
                color: #8fd68f;
            }
            .note {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-top: var(--space-4);
                line-height: 1.5;
            }
            .support-form {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
            }
            .doc-footer {
                margin-top: var(--space-10);
                padding-top: var(--space-6);
                border-top: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                text-align: center;
            }
            .doc-footer a {
                color: var(--accent);
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
            }
            .doc-footer a:hover {
                text-decoration: underline;
            }
        `,
    ];

    constructor() {
        super();
        this._replyEmail = '';
        this._subject = '';
        this._message = '';
        this._status = { kind: 'idle', i18nKey: '' };
    }

    _onReplyInput(e) {
        this._replyEmail = e.detail.value;
    }

    _onSubjectInput(e) {
        this._subject = e.detail.value;
    }

    _onMessageInput(e) {
        this._message = e.detail.value;
    }

    _goHome() {
        this.navigate('landing', {});
    }

    _validate() {
        const s = this._subject.trim();
        const m = this._message.trim();
        if (!s) {
            return { i18nKey: 'support_page.err_subject' };
        }
        if (!m) {
            return { i18nKey: 'support_page.err_message' };
        }
        const re = this._replyEmail.trim();
        if (re.length > 0 && !isValidEmail(re)) {
            return { i18nKey: 'support_page.err_reply_email' };
        }
        return null;
    }

    _submit(e) {
        e.preventDefault();
        const err = this._validate();
        if (err) {
            this._status = { kind: 'error', i18nKey: err.i18nKey };
            return;
        }
        const subject = this._subject.trim().slice(0, MAX_SUBJECT);
        const message = this._message.trim().slice(0, MAX_MESSAGE);
        const re = this._replyEmail.trim();
        let bodyText = message;
        if (re) {
            bodyText = this.t('support_page.mail_line_contact', { email: re }) + '\n\n' + message;
        }
        const href =
            'mailto:' +
            SUPPORT_EMAIL +
            '?subject=' +
            encodeURIComponent(subject) +
            '&body=' +
            encodeURIComponent(bodyText);
        if (href.length > MAX_MAILTO_HREF) {
            this._status = { kind: 'error', i18nKey: 'support_page.err_too_long' };
            return;
        }
        this._status = { kind: 'ok', i18nKey: 'support_page.status_opening' };
        window.location.href = href;
    }

    render() {
        const st = this._status;
        const statusText = st.i18nKey.length > 0 ? this.t(st.i18nKey) : '';
        return html`
            <div class="back-row">
                <glass-button variant="ghost" @click=${this._goHome}>
                    <platform-icon name="arrow-left" size="18"></platform-icon>
                    ${this.t('support_page.back_home')}
                </glass-button>
            </div>
            <div class="page-head">
                <h1>${this.t('support_page.title')}</h1>
                <p class="lede">${this.t('support_page.lede')}</p>
            </div>

            <div class="stack">
                <glass-card compact>
                    <p class="section-title">${this.t('support_page.email_section_title')}</p>
                    <div class="email-row">
                        <div class="icon-wrap" aria-hidden="true">
                            <platform-icon name="mail" size="20"></platform-icon>
                        </div>
                        <div>
                            <a href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a>
                        </div>
                    </div>
                </glass-card>

                <glass-card>
                    <p class="section-title">${this.t('support_page.form_section_title')}</p>
                    <form class="support-form" @submit=${this._submit}>
                        <platform-field
                            type="string"
                            input-type="email"
                            mode="edit"
                            .label=${this.t('support_page.field_reply_email')}
                            .value=${this._replyEmail}
                            @change=${this._onReplyInput}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('support_page.field_subject') + ' ' + this.t('support_page.required_mark')}
                            .value=${this._subject}
                            @change=${this._onSubjectInput}
                        ></platform-field>
                        <platform-field
                            type="text"
                            mode="edit"
                            .label=${this.t('support_page.field_message') + ' ' + this.t('support_page.required_mark')}
                            .value=${this._message}
                            @change=${this._onMessageInput}
                        ></platform-field>
                        <div class="actions">
                            <glass-button type="submit">${this.t('support_page.submit')}</glass-button>
                        </div>
                        <p
                            class="status ${st.kind === 'error' ? 'is-error' : ''} ${st.kind === 'ok' ? 'is-ok' : ''}"
                            role="status"
                            aria-live="polite"
                        >
                            ${statusText}
                        </p>
                        <p class="note">${this.t('support_page.note_mailto')}</p>
                    </form>
                </glass-card>
            </div>

            <div class="doc-footer">
                <a class="doc" href="/documentation/">
                    <platform-icon name="book-open" size="16"></platform-icon>
                    <span>${this.t('support_page.doc_link')}</span>
                </a>
            </div>
        `;
    }
}

customElements.define('support-page', SupportPage);
