/**
 * Полоса runtime-статуса free-pool провайдеров на вкладке скоринга.
 * Только props; фабрики не импортирует.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatDurationSeconds } from '@platform/lib/utils/format-duration.js';
import '@platform/lib/components/platform-help-hint.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export const LLM_PROVIDER_ERROR_CLASS_I18N = Object.freeze({
    rate_limited: 'settings_page.model_scoring.error_rate_limited',
    payment_required: 'settings_page.model_scoring.error_payment_required',
    auth_rejected: 'settings_page.model_scoring.error_auth_rejected',
    timeout: 'settings_page.model_scoring.error_timeout',
    transient: 'settings_page.model_scoring.error_transient',
    http_error: 'settings_page.model_scoring.error_http_error',
    transport: 'settings_page.model_scoring.error_transport',
    content_filter: 'settings_page.model_scoring.error_content_filter',
    unspecified: 'settings_page.model_scoring.error_unspecified',
});

export function llmProviderErrorClassLabel(t: Record<string, any>, errorClass: string) {
    const key = (LLM_PROVIDER_ERROR_CLASS_I18N as Record<string, string>)[errorClass];
    if (key === undefined) {
        throw new Error(`unknown error_class ${errorClass}`);
    }
    return (t as (key: string) => string)(key);
}

export function llmProviderErrorClassIsBlocking(errorClass: string) {
    return errorClass === 'payment_required' || errorClass === 'auth_rejected';
}

export class LlmProviderStatusStrip extends PlatformElement {
    static i18nNamespace = 'frontend';

    static override properties: PropertyDeclarations = {
        providers: { attribute: false },
    }
    declare providers: unknown;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .strip {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                font-size: var(--text-xs);
                line-height: 1.2;
            }
            .dot {
                width: 8px;
                height: 8px;
                border-radius: var(--radius-full);
                flex-shrink: 0;
            }
            .chip[data-tone="success"] .dot { background: var(--success); }
            .chip[data-tone="warning"] .dot { background: var(--warning); }
            .chip[data-tone="error"] .dot { background: var(--error); }
            .chip[data-tone="tertiary"] .dot { background: var(--text-tertiary); }
            .slug {
                font-family: var(--font-mono);
                color: var(--text-primary);
            }
            .meta {
                color: var(--text-tertiary);
            }
        `,
    ];

    _tone(provider: Record<string, any>) {
        if (provider.availability === 'not_configured') {
            return 'tertiary';
        }
        if (
            llmProviderErrorClassIsBlocking(provider.error_class)
            || (provider.last_probe !== null && provider.last_probe.ok === false)
        ) {
            return 'error';
        }
        if (provider.availability === 'cooldown') {
            return 'warning';
        }
        if (provider.availability === 'available') {
            return 'success';
        }
        throw new Error(`llm-provider-status-strip: unknown availability ${provider.availability}`);
    }

    _chipMeta(provider: Record<string, any>) {
        if (provider.availability === 'not_configured') {
            return this.t('settings_page.model_scoring.meta_no_key');
        }
        if (provider.availability === 'cooldown') {
            if (typeof provider.http_status === 'number') {
                return String(provider.http_status);
            }
            if (typeof provider.cooldown_seconds === 'number') {
                return formatDurationSeconds(provider.cooldown_seconds);
            }
            return this.t('settings_page.model_scoring.status_cooldown');
        }
        if (
            provider.last_probe !== null
            && provider.last_probe.ok === false
            && provider.last_probe.error_class !== null
        ) {
            return llmProviderErrorClassLabel((key: string) => this.t(key), provider.last_probe.error_class);
        }
        return '';
    }

    _hintText(provider: Record<string, any>) {
        const parts: any[] = [];
        const translate = (key: string) => this.t(key);
        if (provider.error_class !== null) {
            parts.push(llmProviderErrorClassLabel(translate, provider.error_class));
        }
        if (typeof provider.error_text === 'string' && provider.error_text !== '') {
            parts.push(provider.error_text);
        }
        if (
            provider.last_probe !== null
            && provider.last_probe.ok === false
            && provider.last_probe.error_class !== null
        ) {
            const probeLabel = llmProviderErrorClassLabel(translate, provider.last_probe.error_class);
            if (!parts.includes(probeLabel)) {
                parts.push(probeLabel);
            }
        }
        if (
            provider.last_probe !== null
            && typeof provider.last_probe.error_text === 'string'
            && provider.last_probe.error_text !== ''
            && provider.last_probe.error_text !== provider.error_text
        ) {
            parts.push(provider.last_probe.error_text);
        }
        return parts.join('\n');
    }

    override render(): TemplateResult {
        if (!Array.isArray(this.providers)) {
            throw new Error('llm-provider-status-strip: providers must be an array');
        }
        return html`
            <div class="strip">
                ${this.providers.map((provider) => {
                    if (!provider || typeof provider !== 'object') {
                        throw new Error('llm-provider-status-strip: provider must be an object');
                    }
                    const meta = this._chipMeta(provider);
                    const hint = this._hintText(provider);
                    return html`
                        <span class="chip" data-tone=${this._tone(provider)}>
                            <span class="dot"></span>
                            <span class="slug">${provider.provider}</span>
                            ${meta === '' ? nothing : html`<span class="meta">${meta}</span>`}
                            ${hint === ''
                                ? nothing
                                : html`<platform-help-hint .text=${hint}></platform-help-hint>`}
                        </span>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('llm-provider-status-strip', LlmProviderStatusStrip);
