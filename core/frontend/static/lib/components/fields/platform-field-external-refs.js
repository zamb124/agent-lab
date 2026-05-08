import { html, css, nothing } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

/**
 * Ссылки на записи внешних систем: `attributes.external_refs` — объект
 * { [providerId]: { record_id, last_seen_at?, account_key?, raw_version? } }.
 * Редактирование не предусмотрено: значения приходят от интеграций.
 */
export class PlatformFieldExternalRefs extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: Object },
        mode: { type: String },
        disabled: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            .cards {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                padding: var(--space-3);
            }

            .provider {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: var(--field-pill-label-letter);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
                word-break: break-word;
            }

            .row {
                display: grid;
                grid-template-columns: minmax(100px, 0.35fr) 1fr;
                gap: var(--space-2);
                font-size: var(--text-xs);
                margin-top: var(--space-1);
            }

            .k {
                color: var(--text-tertiary);
            }

            .v {
                color: var(--text-primary);
                font-family: var(--font-mono);
                word-break: break-word;
            }

            .readonly-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.mode = 'view';
        this.disabled = false;
    }

    _entries() {
        const v = this.value;
        if (v == null || typeof v !== 'object' || Array.isArray(v)) {
            return [];
        }
        return Object.entries(v).filter(
            ([, payload]) => payload != null && typeof payload === 'object' && !Array.isArray(payload),
        );
    }

    _scalar(payload, key) {
        const x = payload[key];
        if (x == null) {
            return '';
        }
        if (typeof x === 'object') {
            return JSON.stringify(x);
        }
        return String(x);
    }

    _renderCard(providerId, payload) {
        const recordId = this._scalar(payload, 'record_id');
        const lastSeen = this._scalar(payload, 'last_seen_at');
        const accountKey = this._scalar(payload, 'account_key');
        const rawVersion = this._scalar(payload, 'raw_version');
        return html`
            <div class="card">
                <div class="provider">${providerId}</div>
                ${recordId
                    ? html`<div class="row">
                          <span class="k">${this.t('platform_field.external_refs_record_id')}</span>
                          <span class="v">${recordId}</span>
                      </div>`
                    : nothing}
                ${lastSeen
                    ? html`<div class="row">
                          <span class="k">${this.t('platform_field.external_refs_last_seen')}</span>
                          <span class="v">${lastSeen}</span>
                      </div>`
                    : nothing}
                ${accountKey
                    ? html`<div class="row">
                          <span class="k">${this.t('platform_field.external_refs_account_key')}</span>
                          <span class="v">${accountKey}</span>
                      </div>`
                    : nothing}
                ${rawVersion
                    ? html`<div class="row">
                          <span class="k">${this.t('platform_field.external_refs_raw_version')}</span>
                          <span class="v">${rawVersion}</span>
                      </div>`
                    : nothing}
            </div>
        `;
    }

    render() {
        const entries = this._entries();
        if (entries.length === 0) {
            return html`<span class="field-pill-empty">${this.t('platform_field.external_refs_empty')}</span>`;
        }
        const body = html`<div class="cards">${entries.map(([id, p]) => this._renderCard(id, p))}</div>`;
        if (this.mode === 'edit' && this.disabled) {
            return html`
                ${body}
                <div class="readonly-hint">${this.t('platform_field.external_refs_readonly')}</div>
            `;
        }
        return body;
    }
}

customElements.define('platform-field-external-refs', PlatformFieldExternalRefs);
