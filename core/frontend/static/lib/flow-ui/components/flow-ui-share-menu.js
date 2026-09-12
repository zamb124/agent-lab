/**
 * ``<flow-ui-share-menu>`` — меню «Поделиться» (share grant viewer/editor) и «Встроить»
 * (ссылка на embed-страницу) в topbar ``<platform-flow-ui>``. Хост даёт ``createShare``/``revokeShare``;
 * события ``flow-ui-share-created``/``flow-ui-share-revoked`` всплывают наружу (composed) сквозь хост.
 */

import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { copyTextToClipboard } from '../../utils/clipboard.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { flowUIText } from '../utils/text.js';
import { chromeIconButtonStyles } from './chrome-icon-button.styles.js';

const IDLE_SHARE = Object.freeze({ loading: false, url: '', grantId: '', permission: 'viewer', copied: false, error: '' });

export class FlowUIShareMenu extends LitElement {
    static properties = {
        host: { attribute: false },
        locale: { type: String },
        canShare: { type: Boolean, attribute: 'can-share' },
        embedPageUrl: { type: String, attribute: 'embed-page-url' },
        _share: { state: true },
        _embedCopied: { state: true },
    };

    static styles = [chromeIconButtonStyles, css`
        :host { display: contents; }
        details { position: relative; }
        details > summary { list-style: none; cursor: pointer; }
        details > summary::-webkit-details-marker { display: none; }
        .card {
            position: absolute; inset: calc(100% + 9px) 0 auto auto; z-index: 10;
            width: min(320px, calc(100vw - 28px));
            padding: var(--space-4, 16px);
            display: grid;
            gap: var(--space-3, 12px);
            border: 1px solid var(--glass-border-medium, var(--flow-ui-border-strong));
            border-radius: var(--radius-2xl, 25px);
            background: var(--glass-solid-strong, var(--flow-ui-panel-strong, var(--flow-ui-panel)));
            box-shadow: var(--glass-shadow-strong, var(--flow-ui-panel-shadow));
        }
        .title { font-weight: 650; font-size: var(--font-size-sm, 14px); letter-spacing: -.01em; color: var(--flow-ui-heading, var(--text-primary)); }
        .copy { color: var(--flow-ui-muted, var(--text-tertiary)); font-size: var(--font-size-xs, 12px); line-height: 1.45; }
        .options { display: flex; flex-direction: column; gap: var(--space-2, 8px); }
        .share-btn {
            display: inline-flex; align-items: center; justify-content: center; width: 100%;
            min-height: 36px; padding: 8px 16px; border: none; border-radius: var(--btn-radius, 22px);
            font-family: inherit; font-size: var(--font-size-sm, 14px); font-weight: 400; line-height: 20px;
            white-space: nowrap; cursor: pointer; user-select: none;
            transition: var(--motion-transition-interactive, background .15s ease, box-shadow .15s ease);
        }
        .share-btn.secondary { color: var(--platform-btn-secondary-text, #99A6F9); background: var(--platform-btn-secondary-bg, rgba(153, 166, 249, 0.15)); }
        .share-btn.secondary:hover:not(:disabled) {
            background: var(--platform-btn-secondary-bg-hover, rgba(153, 166, 249, 0.1));
            box-shadow: var(--platform-btn-secondary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.2));
        }
        .share-btn.primary { color: var(--platform-btn-primary-text, #ffffff); background: var(--platform-btn-primary-bg, #99A6F9); box-shadow: var(--platform-btn-primary-shadow, none); }
        .share-btn.primary:hover:not(:disabled) {
            background: var(--platform-btn-primary-bg-hover, #8794F0);
            box-shadow: var(--platform-btn-primary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.6));
        }
        .share-btn.ghost { color: var(--text-secondary, var(--flow-ui-muted)); background: transparent; }
        .share-btn.ghost:hover:not(:disabled) { color: var(--text-primary, var(--flow-ui-text)); background: var(--platform-btn-secondary-bg, rgba(153, 166, 249, 0.12)); }
        .share-btn:disabled { opacity: .5; cursor: wait; }
        .result { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-2, 8px); align-items: center; }
        .result input {
            min-width: 0; height: 36px; padding: 0 14px;
            border: 1px solid var(--border-default, var(--flow-ui-border)); border-radius: var(--btn-radius, 22px);
            background: var(--flow-ui-input, var(--glass-solid-subtle)); color: var(--flow-ui-text);
            font: inherit; font-size: var(--font-size-sm, 14px);
        }
        .error { color: var(--error, #ff8da3); font-size: 12px; }
    `];

    constructor() {
        super();
        this.host = null;
        this.locale = 'en';
        this.canShare = false;
        this.embedPageUrl = '';
        this._share = IDLE_SHARE;
        this._embedCopied = false;
    }

    async _createShare(permission) {
        this._share = { ...IDLE_SHARE, loading: true, permission };
        try {
            const result = await this.host.createShare({ permission, redactedPaths: [] });
            this._share = { ...IDLE_SHARE, url: result.share_url, grantId: result.grant.grant_id, permission };
            this.dispatchEvent(new CustomEvent('flow-ui-share-created', { bubbles: true, composed: true, detail: result }));
        } catch (error) {
            this._share = { ...IDLE_SHARE, permission, error: error instanceof Error ? error.message : String(error) };
        }
    }

    async _revokeShare() {
        const grantId = this._share.grantId;
        if (!grantId) throw new Error('flow-ui: no active share grant to revoke');
        this._share = { ...this._share, loading: true, error: '' };
        try {
            await this.host.revokeShare(grantId);
            this._share = { ...IDLE_SHARE, permission: this._share.permission };
            this.dispatchEvent(new CustomEvent('flow-ui-share-revoked', { bubbles: true, composed: true, detail: { grant_id: grantId } }));
        } catch (error) {
            this._share = { ...this._share, loading: false, error: error instanceof Error ? error.message : String(error) };
        }
    }

    async _copy(text, onCopied, selector) {
        try {
            await copyTextToClipboard(text);
            onCopied(true);
        } catch {
            this.renderRoot.querySelector(selector)?.select();
            onCopied(false);
        }
    }

    _shareMenu() {
        if (!this.canShare) return nothing;
        const locale = this.locale;
        const share = this._share;
        return html`<details class="share">
            <summary class="chrome-icon-btn" aria-label=${flowUIText(locale, 'share_aria')} title=${flowUIText(locale, 'share')}>${flowUIGlyph('share', 18, this.host.platformUiOrigin)}</summary>
            <div class="card share-card">
                <div><div class="title">${flowUIText(locale, 'share_title')}</div><div class="copy">${flowUIText(locale, 'share_description')}</div></div>
                <div class="options">
                    <button type="button" class="share-btn secondary" ?disabled=${share.loading} @click=${() => this._createShare('viewer')}>${flowUIText(locale, 'share_view_only')}</button>
                    <button type="button" class="share-btn primary" ?disabled=${share.loading} @click=${() => this._createShare('editor')}>${flowUIText(locale, 'share_can_interact')}</button>
                </div>
                ${share.loading ? html`<div class="copy">${flowUIText(locale, 'share_creating')}</div>` : nothing}
                ${share.url ? html`
                    <div class="result share-result">
                        <input readonly .value=${share.url} aria-label=${flowUIText(locale, 'share_link')}>
                        <button type="button" class="share-btn secondary" @click=${() => this._copy(share.url, (copied) => { this._share = { ...this._share, copied }; }, '.share-result input')}>${flowUIText(locale, share.copied ? 'share_copied' : 'share_copy')}</button>
                    </div>
                    <button type="button" class="share-btn ghost" ?disabled=${share.loading} @click=${() => this._revokeShare()}>${flowUIText(locale, 'share_revoke')}</button>
                ` : nothing}
                ${share.error ? html`<div class="error" role="alert">${share.error}</div>` : nothing}
            </div>
        </details>`;
    }

    _embedMenu() {
        const pageUrl = this.embedPageUrl;
        if (pageUrl === '') return nothing;
        const locale = this.locale;
        return html`<details class="embed">
            <summary class="chrome-icon-btn" aria-label=${flowUIText(locale, 'embed_aria')} title=${flowUIText(locale, 'embed')}>${flowUIGlyph('globe', 18, this.host.platformUiOrigin)}</summary>
            <div class="card embed-card">
                <div><div class="title">${flowUIText(locale, 'embed_title')}</div><div class="copy">${flowUIText(locale, 'embed_page_description')}</div></div>
                <div class="result embed-result">
                    <input readonly .value=${pageUrl} aria-label=${flowUIText(locale, 'embed_page_url')}>
                    <button type="button" class="share-btn secondary" @click=${() => this._copy(pageUrl, (copied) => { this._embedCopied = copied; }, '.embed-result input')}>${flowUIText(locale, this._embedCopied ? 'embed_copied' : 'embed_copy')}</button>
                </div>
            </div>
        </details>`;
    }

    render() {
        if (this.host === null) return nothing;
        return html`${this._embedMenu()}${this._shareMenu()}`;
    }
}

if (!customElements.get('flow-ui-share-menu')) customElements.define('flow-ui-share-menu', FlowUIShareMenu);
