/**
 * Публичная страница поддержки: email + форма, отправка через mailto (без backend).
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import { isValidEmail } from '@platform/lib/utils/validators.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

const SUPPORT_EMAIL = 'helpme@humanitec.ru';
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

    static styles = [PlatformPage.styles, ...marketingPublicContentPageStyles];

    constructor() {
        super();
        this._replyEmail = '';
        this._subject = '';
        this._message = '';
        this._status = { kind: 'idle', i18nKey: '' };
    }

    connectedCallback() {
        super.connectedCallback();
        queueMicrotask(() => this._syncDocumentMeta());
    }

    _syncDocumentMeta() {
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        applyPublicDocumentMeta({
            title: this.t('meta.support_title', {}, 'landing'),
            description: this.t('meta.support_description', {}, 'landing'),
            canonicalUrl: `${origin}/support`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
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

    _validate() {
        const subject = this._subject.trim();
        const message = this._message.trim();
        if (!subject) {
            return { i18nKey: 'support_page.err_subject' };
        }
        if (!message) {
            return { i18nKey: 'support_page.err_message' };
        }
        const replyEmail = this._replyEmail.trim();
        if (replyEmail.length > 0 && !isValidEmail(replyEmail)) {
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
        const replyEmail = this._replyEmail.trim();
        let bodyText = message;
        if (replyEmail) {
            bodyText = this.t('support_page.mail_line_contact', { email: replyEmail }) + '\n\n' + message;
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
        const status = this._status;
        const statusText = status.i18nKey.length > 0 ? this.t(status.i18nKey) : '';
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                <div class="marketing-content">
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title">${this.t('support_page.title')}</h1>
                        <p class="marketing-content-lede">${this.t('support_page.lede')}</p>
                    </header>

                    <div class="marketing-content-stack">
                        <section class="marketing-content-panel glass-medium marketing-content-panel-compact">
                            <p class="marketing-content-section-label">${this.t('support_page.email_section_title')}</p>
                            <div class="marketing-contact-row">
                                <div class="marketing-contact-icon" aria-hidden="true">
                                    <platform-icon name="mail" size="20"></platform-icon>
                                </div>
                                <div>
                                    <a class="marketing-contact-link" href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a>
                                </div>
                            </div>
                        </section>

                        <section class="marketing-content-panel glass-medium">
                            <p class="marketing-content-section-label">${this.t('support_page.form_section_title')}</p>
                            <form class="marketing-form-stack" @submit=${this._submit}>
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
                                <div class="marketing-form-actions">
                                    <platform-button type="submit" variant="primary">
                                        ${this.t('support_page.submit')}
                                    </platform-button>
                                </div>
                                <p
                                    class="marketing-form-status ${status.kind === 'error' ? 'is-error' : ''} ${status.kind === 'ok' ? 'is-ok' : ''}"
                                    role="status"
                                    aria-live="polite"
                                >
                                    ${statusText}
                                </p>
                                <p class="marketing-form-note">${this.t('support_page.note_mailto')}</p>
                            </form>
                        </section>
                    </div>

                    <footer class="marketing-content-aside">
                        <a class="marketing-content-aside-link" href="/documentation/">
                            <platform-icon name="book-open" size="16"></platform-icon>
                            <span>${this.t('support_page.doc_link')}</span>
                        </a>
                    </footer>
                </div>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('support-page', SupportPage);
