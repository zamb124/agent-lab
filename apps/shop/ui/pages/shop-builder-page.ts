/**
 * Внешний вид витрины: шаблонные пресеты + акцентный цвет + живое превью.
 * Директор выбирает шаблон и цвет — витрина пересобирается автоматически.
 */

import { html, css } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';

const PRESETS = ['menu', 'grid', 'compact'] as const;

const MODES = ['dark', 'light'] as const;

const ACCENTS = ['#e2553f', '#f2a33c', '#34c47c', '#3f8cff', '#9b5de5', '#ef476f', '#111827', '#0f766e'];

export class ShopBuilderPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ResourceController;
    private _updateOp: OpController;
    declare _preset: string;
    declare _accent: string;
    declare _mode: string;
    declare _device: string;
    private _savedPreset = 'menu';
    private _savedAccent = '#e2553f';
    private _savedMode = 'dark';
    declare _loadAttempted: boolean;
    private _hydrated = false;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        _preset: { state: true },
        _accent: { state: true },
        _mode: { state: true },
        _device: { state: true },
        _loadAttempted: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow: hidden; }
            .layout {
                display: grid;
                grid-template-columns: 340px 1fr;
                height: 100%;
            }
            .panel {
                padding: var(--space-5) var(--space-6);
                overflow-y: auto;
                border-right: 1px solid var(--glass-border-subtle);
            }
            .section { margin-bottom: var(--space-5); }
            .label { font-size: var(--text-sm); font-weight: var(--font-medium); color: var(--text-secondary); margin-bottom: var(--space-2); }
            .presets { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-2); }
            .preset {
                border: 2px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-2);
                background: var(--bg-surface);
                cursor: pointer;
                text-align: center;
                color: var(--text-primary);
                transition: border-color 0.15s ease, transform 0.15s ease;
            }
            .preset:hover { transform: translateY(-1px); }
            .preset.active { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent); }
            .wire {
                height: 72px;
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--text-primary) 5%, transparent);
                overflow: hidden;
                display: flex;
                flex-direction: column;
                gap: 4px;
                padding: 6px;
                margin-bottom: var(--space-2);
            }
            .wire .hero { height: 16px; border-radius: 4px; background: var(--accent); opacity: 0.85; }
            .wire .ln { height: 9px; border-radius: 3px; background: color-mix(in srgb, var(--text-primary) 22%, transparent); display: flex; gap: 4px; align-items: center; }
            .wire .ln::before { content: ''; width: 9px; height: 9px; border-radius: 3px; background: var(--accent); flex-shrink: 0; }
            .wire .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; flex: 1; }
            .wire .tile { border-radius: 4px; background: color-mix(in srgb, var(--text-primary) 22%, transparent); position: relative; }
            .wire .tile::after { content: ''; position: absolute; left: 3px; right: 3px; bottom: 3px; height: 4px; border-radius: 2px; background: var(--accent); opacity: 0.8; }
            .wire .dense { height: 7px; border-radius: 3px; background: color-mix(in srgb, var(--text-primary) 22%, transparent); }
            .wire .dense::after { content: ''; display: block; margin-left: auto; width: 12px; height: 7px; border-radius: 3px; background: var(--accent); opacity: 0.8; }
            .preset .name { font-size: var(--text-xs); font-weight: var(--font-medium); display: block; padding-bottom: var(--space-1); }
            .swatches { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .swatch {
                width: 40px;
                height: 40px;
                border-radius: var(--radius-md);
                border: 3px solid transparent;
                cursor: pointer;
            }
            .swatch.active { border-color: var(--text-primary); }
            .modes { display: flex; background: var(--bg-inset); border-radius: var(--radius-md); padding: 4px; gap: 4px; }
            .mode {
                flex: 1;
                border: 0;
                border-radius: var(--radius-sm);
                padding: var(--space-2) var(--space-3);
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }
            .mode.active { background: var(--bg-surface); color: var(--text-primary); box-shadow: 0 1px 4px rgba(0,0,0,0.18); }
            .actions { display: flex; gap: var(--space-2); }
            .preview {
                position: relative;
                background: color-mix(in srgb, var(--text-primary) 3%, transparent);
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .preview iframe {
                width: 420px;
                height: 100%;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: #0f1218;
                margin: var(--space-8) 0 var(--space-4);
                transition: width 0.2s ease;
            }
            .preview iframe.desktop {
                width: min(960px, calc(100% - var(--space-8)));
            }
            .preview-bar {
                position: absolute;
                top: var(--space-2);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            .preview-url {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .devices { display: flex; gap: var(--space-1); }
            .devices button {
                border: 1px solid var(--glass-border-subtle);
                background: var(--bg-surface);
                color: var(--text-tertiary);
                border-radius: var(--radius-sm);
                width: 30px;
                height: 26px;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .devices button.active { color: var(--accent); border-color: var(--accent); }
            @media (max-width: 900px) {
                .layout { grid-template-columns: 1fr; }
                .preview { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this._preset = 'menu';
        this._accent = '#e2553f';
        this._mode = 'dark';
        this._device = 'phone';
        this._loadAttempted = false;
        this._shops = this.useResource('shop/shops', { autoload: true });
        this._updateOp = this.useOp('shop/shop_update');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._loadAttempted = true;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('shopId')) this._hydrated = false;
        if (!this._hydrated) this._hydrated = this._hydrate();
    }

    private _shop(): Record<string, unknown> | null {
        const row = this._shops.items.find((s) => (s as Record<string, unknown>).shop_id === this.shopId);
        return row === undefined ? null : (row as Record<string, unknown>);
    }

    private _hydrate(): boolean {
        const shop = this._shop();
        if (shop === null) return false;
        const theme = (shop.theme ?? {}) as Record<string, unknown>;
        this._preset = typeof theme.preset === 'string' ? theme.preset : 'menu';
        this._accent = typeof theme.accent_color === 'string' ? theme.accent_color : '#e2553f';
        this._mode = theme.mode === 'light' ? 'light' : 'dark';
        this._savedPreset = this._preset;
        this._savedAccent = this._accent;
        this._savedMode = this._mode;
        return true;
    }

    private get _dirty(): boolean {
        return this._preset !== this._savedPreset || this._accent !== this._savedAccent || this._mode !== this._savedMode;
    }

    private _wireframe(preset: string) {
        if (preset === 'grid') {
            return html`<span class="wire"><span class="hero"></span><span class="tiles"><span class="tile"></span><span class="tile"></span><span class="tile"></span><span class="tile"></span></span></span>`;
        }
        if (preset === 'compact') {
            return html`<span class="wire"><span class="hero"></span><span class="dense"></span><span class="dense"></span><span class="dense"></span><span class="dense"></span></span>`;
        }
        return html`<span class="wire"><span class="hero"></span><span class="ln"></span><span class="ln"></span><span class="ln"></span></span>`;
    }

    private _previewSrc(base: string): string {
        const q = `tpreset=${this._preset}&taccent=${encodeURIComponent(this._accent)}&tmode=${this._mode}`;
        return `${base}${base.includes('?') ? '&' : '?'}${q}`;
    }

    private async _save() {
        const result = await this._updateOp.run({
            shop_id: this.shopId,
            theme: { preset: this._preset, accent_color: this._accent, mode: this._mode },
        });
        if (result !== null) {
            this._savedPreset = this._preset;
            this._savedAccent = this._accent;
            this._savedMode = this._mode;
            await this._shops.load();
            const frame = this.renderRoot?.querySelector<HTMLIFrameElement>('.preview iframe');
            if (frame !== null && frame !== undefined && frame.src !== '') {
                const src = frame.src.split('#')[0] ?? frame.src;
                frame.src = `${src}${src.includes('?') ? '&' : '?'}v=${Date.now()}`;
            }
        }
    }

    override render() {
        const shop = this._shop();
        if (shop === null) {
            return this._shops.loading || !this._loadAttempted
                ? html`<platform-empty-state loading></platform-empty-state>`
                : html`
                    <platform-empty-state icon="store" title=${this.t('builder.shop_not_found')}>
                        <platform-button size="sm" variant="secondary" @click=${() => { this._shops.load(); }}>${this.t('builder.retry')}</platform-button>
                    </platform-empty-state>`;
        }
        const storefrontUrl = typeof shop.storefront_url === 'string' ? shop.storefront_url : '';
        const slug = typeof shop.slug === 'string' ? shop.slug : '';
        const previewPath = shop.status === 'published' && slug !== ''
            ? `/shop/api/v1/public/s/${encodeURIComponent(slug)}`
            : '';
        return html`
            <div class="layout">
                <div class="panel">
                    <shop-page-head
                        .shop=${shopHeadRow(shop)}
                        shop-id=${this.shopId}
                        section=${this.t('routes.shop_builder')}
                    ></shop-page-head>
                    <div class="section">
                        <div class="label">${this.t('builder.preset_label')}</div>
                        <div class="presets">
                            ${PRESETS.map((key) => html`
                                <button
                                    class="preset ${this._preset === key ? 'active' : ''}"
                                    @click=${() => { this._preset = key; }}
                                >
                                    ${this._wireframe(key)}
                                    <span class="name">${this.t(`builder.preset_${key}`)}</span>
                                </button>
                            `)}
                        </div>
                    </div>
                    <div class="section">
                        <div class="label">${this.t('builder.mode_label')}</div>
                        <div class="modes">
                            ${MODES.map((key) => html`
                                <button
                                    class="mode ${this._mode === key ? 'active' : ''}"
                                    @click=${() => { this._mode = key; }}
                                ><platform-icon name=${key === 'dark' ? 'moon' : 'sun'} size="14"></platform-icon> ${this.t(`builder.mode_${key}`)}</button>
                            `)}
                        </div>
                    </div>
                    <div class="section">
                        <div class="label">${this.t('builder.accent_label')}</div>
                        <div class="swatches">
                            ${ACCENTS.map((c) => html`
                                <button
                                    class="swatch ${this._accent === c ? 'active' : ''}"
                                    style="background:${c}"
                                    @click=${() => { this._accent = c; }}
                                ></button>
                            `)}
                        </div>
                    </div>
                    <div class="actions">
                        <platform-button
                            variant="primary"
                            ?busy=${this._updateOp.busy}
                            ?disabled=${!this._dirty}
                            @click=${() => this._save()}
                        >${this.t('builder.save')}</platform-button>
                        <platform-button variant="secondary" ?disabled=${!this._dirty} @click=${() => { this._preset = this._savedPreset; this._accent = this._savedAccent; this._mode = this._savedMode; }}>
                            ${this.t('builder.reset')}
                        </platform-button>
                    </div>
                </div>
                <div class="preview">
                    <div class="preview-bar">
                        <div class="devices">
                            <button class=${this._device === 'phone' ? 'active' : ''} title=${this.t('builder.device_phone')}
                                @click=${() => { this._device = 'phone'; }}
                            ><platform-icon name="smartphone" size="14"></platform-icon></button>
                            <button class=${this._device === 'desktop' ? 'active' : ''} title=${this.t('builder.device_desktop')}
                                @click=${() => { this._device = 'desktop'; }}
                            ><platform-icon name="monitor" size="14"></platform-icon></button>
                        </div>
                        <span class="preview-url">${storefrontUrl}</span>
                    </div>
                    ${previewPath === ''
                        ? html`<platform-empty-state icon="store" title=${this.t('builder.preview_unavailable')}></platform-empty-state>`
                        : html`<iframe class=${this._device === 'desktop' ? 'desktop' : ''} src=${this._previewSrc(previewPath)} title="storefront"></iframe>`}
                </div>
            </div>
        `;
    }
}

customElements.define('shop-builder-page', ShopBuilderPage);
