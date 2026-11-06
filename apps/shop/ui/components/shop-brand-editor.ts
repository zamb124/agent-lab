/**
 * ShopBrandEditor — логотип и обложка витрины как шапка профиля:
 * широкий баннер, круглый логотип поверх левого края. Клик по плитке —
 * загрузка файла; «✨»-фаб рядом — AI-генерация. Изменения сохраняются
 * мгновенно (file_create + shop_update), наружу — событие `updated`.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';

export class ShopBrandEditor extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        shopId: { type: String, attribute: 'shop-id' },
        logoFileId: { type: String, attribute: 'logo-file-id' },
        coverFileId: { type: String, attribute: 'cover-file-id' },
        shopName: { type: String, attribute: 'shop-name' },
        description: { type: String },
    };
    declare shopId: string;
    declare logoFileId: string;
    declare coverFileId: string;
    declare shopName: string;
    declare description: string;

    private _uploadOp: OpController;
    private _updateOp: OpController;
    private _aiCoverOp: OpController;
    private _aiLogoOp: OpController;

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .brand { position: relative; }
            .cover {
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                width: 100%;
                aspect-ratio: 3.4 / 1;
                min-height: 132px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--text-primary) 4%, transparent);
                color: var(--text-tertiary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                overflow: hidden;
                padding: 0;
                transition: border-color var(--motion-duration-micro);
            }
            .cover:hover { border-color: var(--accent); }
            .cover img {
                position: absolute;
                inset: 0;
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .veil {
                position: absolute;
                inset: auto 0 0;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                background: color-mix(in srgb, var(--bg-surface) 82%, transparent);
                color: var(--text-secondary);
                font-size: var(--text-2xs, 10px);
                padding: var(--space-1);
            }
            .fab {
                position: absolute;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-surface);
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-xs);
                padding: var(--space-1) var(--space-2);
                cursor: pointer;
                transition: color var(--motion-duration-micro),
                            border-color var(--motion-duration-micro);
            }
            .fab:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
            .fab:disabled { opacity: 0.5; cursor: default; }
            .fab.cover-ai { top: var(--space-2); right: var(--space-2); }
            .fab.logo-ai {
                left: calc(var(--space-4) + 64px);
                bottom: calc(var(--space-1) * -1);
                width: 30px;
                height: 30px;
                padding: 0;
                border-radius: 50%;
            }
            .logo {
                position: absolute;
                left: var(--space-4);
                bottom: 0;
                transform: translateY(50%);
                width: 88px;
                height: 88px;
                border-radius: 50%;
                border: 3px solid var(--bg-surface);
                background: var(--bg-surface);
                color: var(--text-tertiary);
                cursor: pointer;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0;
            }
            .logo img {
                position: absolute;
                inset: 0;
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .hint {
                margin-top: calc(44px + var(--space-3));
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.shopId = '';
        this.logoFileId = '';
        this.coverFileId = '';
        this.shopName = '';
        this.description = '';
        this._uploadOp = this.useOp('platform/file_create');
        this._updateOp = this.useOp('shop/shop_update');
        this._aiCoverOp = this.useOp('shop/ai_generate_cover');
        this._aiLogoOp = this.useOp('shop/ai_generate_logo');
    }

    private _pickFile(kind: 'logo' | 'cover') {
        const input = this.renderRoot?.querySelector<HTMLInputElement>(`#brand-${kind}-input`);
        input?.click();
    }

    private async _saveField(field: 'logo_file_id' | 'cover_file_id', fileId: string) {
        const saved = await this._updateOp.run({ shop_id: this.shopId, [field]: fileId });
        if (saved !== null) this.emit('updated');
    }

    private async _upload(kind: 'logo' | 'cover', event: Event) {
        const input = event.target as HTMLInputElement;
        const file = input.files && input.files[0];
        input.value = '';
        if (!file) return;
        const uploaded = await this._uploadOp.run({
            file,
            spec: buildShopProductFileCreateSpecJson({ shopId: this.shopId }),
        });
        if (uploaded === null || typeof uploaded !== 'object') return;
        const fileId = (uploaded as { file_id?: unknown }).file_id;
        if (typeof fileId !== 'string') return;
        await this._saveField(kind === 'logo' ? 'logo_file_id' : 'cover_file_id', fileId);
    }

    private async _aiGenerate(kind: 'logo' | 'cover') {
        const name = this.shopName.trim();
        if (name === '') return;
        const op = kind === 'logo' ? this._aiLogoOp : this._aiCoverOp;
        const result = await op.run({ shop_id: this.shopId, name, description: this.description });
        if (result === null || typeof result !== 'object') return;
        const fileId = (result as { file_id?: unknown }).file_id;
        if (typeof fileId !== 'string') return;
        await this._saveField(kind === 'logo' ? 'logo_file_id' : 'cover_file_id', fileId);
    }

    private _fileUrl(fileId: string, variant: string): string {
        return `/shop/api/v1/files/download/${fileId}?v=${variant}`;
    }

    override render(): TemplateResult {
        const aiDisabled = this.shopName.trim() === '' || this._uploadOp.busy;
        return html`
            <input id="brand-logo-input" type="file" accept="image/*" hidden @change=${(e: Event) => this._upload('logo', e)}>
            <input id="brand-cover-input" type="file" accept="image/*" hidden @change=${(e: Event) => this._upload('cover', e)}>
            <div class="brand">
                <button class="cover" ?disabled=${this._uploadOp.busy} title=${this.t('settings.cover')} @click=${() => this._pickFile('cover')}>
                    ${this.coverFileId === ''
                        ? html`
                            <platform-icon name="image" size="22"></platform-icon>
                            <span>${this._uploadOp.busy ? this.t('settings.upload') : this.t('settings.cover')}</span>`
                        : html`
                            <img src=${this._fileUrl(this.coverFileId, 'md')} alt="">
                            <span class="veil">${this.t('settings.replace_photo')}</span>`}
                </button>
                <button class="fab cover-ai" ?disabled=${aiDisabled} title=${this.t('settings.ai_cover_hint')} @click=${() => this._aiGenerate('cover')}>
                    ${this._aiCoverOp.busy
                        ? html`<platform-spinner size="14"></platform-spinner>`
                        : html`<platform-icon name="sparkle" size="13"></platform-icon>`}
                    ${this.t('settings.ai_generate_cover')}
                </button>
                <button class="logo" ?disabled=${this._uploadOp.busy} title=${this.t('settings.logo')} @click=${() => this._pickFile('logo')}>
                    ${this.logoFileId === ''
                        ? html`<platform-icon name="image" size="22"></platform-icon>`
                        : html`<img src=${this._fileUrl(this.logoFileId, 'sm!sq')} alt="">`}
                </button>
                <button class="fab logo-ai" ?disabled=${aiDisabled} title=${this.t('settings.ai_logo_hint')} @click=${() => this._aiGenerate('logo')}>
                    ${this._aiLogoOp.busy
                        ? html`<platform-spinner size="14"></platform-spinner>`
                        : html`<platform-icon name="sparkle" size="13"></platform-icon>`}
                </button>
            </div>
            <div class="hint">${this.t('settings.brand_hint')}</div>
        `;
    }
}

customElements.define('shop-brand-editor', ShopBrandEditor);
