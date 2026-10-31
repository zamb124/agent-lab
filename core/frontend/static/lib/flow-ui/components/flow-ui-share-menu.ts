/**
 * ``<flow-ui-share-menu>`` — меню «Поделиться» (share grant viewer/editor) и «Встроить»
 * (ссылка на embed-страницу) в topbar ``<platform-flow-ui>``. Хост даёт ``createShare``/``revokeShare``;
 * события ``flow-ui-share-created``/``flow-ui-share-revoked`` всплывают наружу (composed) сквозь хост.
 */

import { LitElement, css, html, nothing } from 'lit';
import type { FlowUiRecord } from '../runtime/flow-ui-store.js';
import { copyTextToClipboard } from '../../utils/clipboard.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { flowUIText } from '../utils/text.js';
import { chromeIconButtonStyles } from './chrome-icon-button.styles.js';

const IDLE_SHARE = Object.freeze({ loading: false, url: '', grantId: '', permission: 'viewer', copied: false, error: '' });

function presentText(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

interface ShareState {
    loading: boolean;
    url: string;
    grantId: string;
    permission: string;
    copied: boolean;
    error: string;
}

interface FlowUiShareHost {
    platformUiOrigin: string;
    createShare(req: { permission: string; redactedPaths: string[] }): Promise<{ share_url: string; grant: FlowUiRecord }>;
    revokeShare(grantId: string): Promise<void>;
}

export class FlowUIShareMenu extends LitElement {
    declare host: FlowUiShareHost | null;
    declare locale: string;
    declare canShare: boolean;
    declare embedPageUrl: string;
    declare _share: ShareState;
    declare _embedCopied: boolean;

    static override properties = {
        host: { attribute: false },
        locale: { type: String },
        canShare: { type: Boolean, attribute: 'can-share' },
        embedPageUrl: { type: String, attribute: 'embed-page-url' },
        _share: { state: true },
        _embedCopied: { state: true },
    };

    static override styles = [chromeIconButtonStyles, css`
        :host { display: contents; }
        details { position: relative; }
        details > summary { list-style: none; cursor: pointer; }
        details > summary::-webkit-details-marker { display: none; }
        .card {
            position: absolute; inset: calc(100% + 9px) 0 auto auto; z-index: 10;
            width: min(320px, calc(100vw - 28px));
            padding: var(--space-4);
            display: grid;
            gap: var(--space-3);
            border: 1px solid var(--glass-border-medium);
            border-radius: var(--radius-2xl);
            background: var(--glass-solid-strong);
            box-shadow: var(--glass-shadow-strong);
        }
        .title { font-weight: 650; font-size: var(--text-sm); letter-spacing: -.01em; color: var(--flow-ui-heading, var(--text-primary)); }
        .copy { color: var(--flow-ui-muted, var(--text-tertiary)); font-size: var(--text-xs); line-height: 1.45; }
        .options { display: flex; flex-direction: column; gap: var(--space-2); }
        .share-btn {
            display: inline-flex; align-items: center; justify-content: center; width: 100%;
            min-height: 36px; padding: 8px 16px; border: none; border-radius: var(--btn-radius);
            font-family: inherit; font-size: var(--text-sm); font-weight: 400; line-height: 20px;
            white-space: nowrap; cursor: pointer; user-select: none;
            transition: var(--motion-transition-interactive);
        }
        .share-btn.secondary { color: var(--platform-btn-secondary-text); background: var(--platform-btn-secondary-bg); }
        .share-btn.secondary:hover:not(:disabled) {
            background: var(--platform-btn-secondary-bg-hover);
            box-shadow: var(--platform-btn-secondary-shadow-hover);
        }
        .share-btn.primary { color: var(--platform-btn-primary-text); background: var(--platform-btn-primary-bg); box-shadow: var(--platform-btn-primary-shadow); }
        .share-btn.primary:hover:not(:disabled) {
            background: var(--platform-btn-primary-bg-hover);
            box-shadow: var(--platform-btn-primary-shadow-hover);
        }
        .share-btn.ghost { color: var(--text-secondary); background: transparent; }
        .share-btn.ghost:hover:not(:disabled) { color: var(--text-primary); background: var(--platform-btn-secondary-bg); }
        .share-btn:disabled { opacity: .5; cursor: wait; }
        .result { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-2); align-items: center; }
        .result input {
            min-width: 0; height: 36px; padding: 0 14px;
            border: 1px solid var(--border-default); border-radius: var(--btn-radius);
            background: var(--flow-ui-input, var(--glass-solid-subtle)); color: var(--flow-ui-text);
            font: inherit; font-size: var(--text-sm);
        }
        .error { color: var(--error); font-size: 12px; }
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

    private async _createShare(permission: string) {
        this._share = { ...IDLE_SHARE, loading: true, permission };
        try {
            const host = this.host;
        if (!host) return;
        const result = await host.createShare({ permission, redactedPaths: [] });
            this._share = { ...IDLE_SHARE, url: result.share_url, grantId: presentText(result.grant.grant_id), permission };
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
            await this.host?.revokeShare(grantId);
            this._share = { ...IDLE_SHARE, permission: this._share.permission };
            this.dispatchEvent(new CustomEvent('flow-ui-share-revoked', { bubbles: true, composed: true, detail: { grant_id: grantId } }));
        } catch (error) {
            this._share = { ...this._share, loading: false, error: error instanceof Error ? error.message : String(error) };
        }
    }

    private async _copy(text: string, onCopied: (copied: boolean) => void) {
        await copyTextToClipboard(text);
        onCopied(true);
    }

    _shareMenu() {
        if (!this.canShare) return nothing;
        const locale = this.locale;
        const share = this._share;
        return html`<details class="share">
            <summary class="chrome-icon-btn" aria-label=${flowUIText(locale, 'share_aria')} title=${flowUIText(locale, 'share')}>${flowUIGlyph('share', 18, this.host === null ? '' : this.host.platformUiOrigin)}</summary>
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
                        <button type="button" class="share-btn secondary" @click=${() => this._copy(share.url, (copied: boolean) => { this._share = { ...this._share, copied }; })}>${flowUIText(locale, share.copied ? 'share_copied' : 'share_copy')}</button>
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
            <summary class="chrome-icon-btn" aria-label=${flowUIText(locale, 'embed_aria')} title=${flowUIText(locale, 'embed')}>${flowUIGlyph('globe', 18, this.host === null ? '' : this.host.platformUiOrigin)}</summary>
            <div class="card embed-card">
                <div><div class="title">${flowUIText(locale, 'embed_title')}</div><div class="copy">${flowUIText(locale, 'embed_page_description')}</div></div>
                <div class="result embed-result">
                    <input readonly .value=${pageUrl} aria-label=${flowUIText(locale, 'embed_page_url')}>
                    <button type="button" class="share-btn secondary" @click=${() => this._copy(pageUrl, (copied: boolean) => { this._embedCopied = copied; })}>${flowUIText(locale, this._embedCopied ? 'embed_copied' : 'embed_copy')}</button>
                </div>
            </div>
        </details>`;
    }

    override render() {
        if (this.host === null) return nothing;
        return html`${this._embedMenu()}${this._shareMenu()}`;
    }
}

if (!customElements.get('flow-ui-share-menu')) customElements.define('flow-ui-share-menu', FlowUIShareMenu);
