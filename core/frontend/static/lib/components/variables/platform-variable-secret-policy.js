/**
 * Secret policy selector — plain / secret_private / secret_shared cards.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

const POLICY_PLAIN = 'plain';
const POLICY_PRIVATE = 'secret_private';
const POLICY_SHARED = 'secret_shared';

function _policyFromFlags(secret, sharedForExecution) {
    if (!secret) {
        return POLICY_PLAIN;
    }
    if (sharedForExecution) {
        return POLICY_SHARED;
    }
    return POLICY_PRIVATE;
}

export class PlatformVariableSecretPolicy extends PlatformElement {
    static i18nNamespace = 'company_variables';

    static properties = {
        secret: { type: Boolean },
        sharedForExecution: { type: Boolean, attribute: 'shared-for-execution' },
        readonly: { type: Boolean, reflect: true },
        disabled: { type: Boolean, reflect: true },
    };

    static styles = css`
        :host { display: block; }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: var(--space-3);
        }
        .card {
            display: flex;
            flex-direction: column;
            gap: var(--space-1);
            padding: var(--space-3);
            border: 1px solid var(--glass-border-subtle);
            border-radius: var(--radius-md);
            background: var(--glass-solid-medium);
            cursor: pointer;
            text-align: left;
            color: var(--text-secondary);
            transition: var(--motion-transition-interactive);
        }
        .card:hover:not(:disabled) {
            border-color: var(--accent);
            color: var(--text-primary);
        }
        .card.active {
            border-color: var(--accent);
            background: var(--accent-subtle);
            color: var(--text-primary);
        }
        .card:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .card-title {
            font-size: var(--text-sm);
            font-weight: var(--font-semibold);
        }
        .card-hint {
            font-size: var(--text-xs);
            line-height: 1.4;
        }
    `;

    constructor() {
        super();
        this.secret = false;
        this.sharedForExecution = false;
        this.readonly = false;
        this.disabled = false;
    }

    _currentPolicy() {
        return _policyFromFlags(this.secret, this.sharedForExecution);
    }

    _select(policy) {
        if (this.readonly || this.disabled) {
            return;
        }
        let secret = false;
        let sharedForExecution = false;
        if (policy === POLICY_PRIVATE) {
            secret = true;
        } else if (policy === POLICY_SHARED) {
            secret = true;
            sharedForExecution = true;
        }
        this.dispatchEvent(new CustomEvent('change', {
            bubbles: true,
            composed: true,
            detail: { secret, shared_for_execution: sharedForExecution },
        }));
    }

    _renderCard(policy, titleKey, hintKey) {
        const active = this._currentPolicy() === policy;
        return html`
            <button
                type="button"
                class="card ${active ? 'active' : ''}"
                ?disabled=${this.readonly || this.disabled}
                @click=${() => this._select(policy)}
            >
                <span class="card-title">${this.t(`editor.${titleKey}`)}</span>
                <span class="card-hint">${this.t(`editor.${hintKey}`)}</span>
            </button>
        `;
    }

    render() {
        return html`
            <div class="cards">
                ${this._renderCard(POLICY_PLAIN, 'secret_policy_plain', 'secret_policy_plain_hint')}
                ${this._renderCard(POLICY_PRIVATE, 'secret_policy_private', 'secret_policy_private_hint')}
                ${this._renderCard(POLICY_SHARED, 'secret_policy_shared', 'secret_policy_shared_hint')}
            </div>
        `;
    }
}

customElements.define('platform-variable-secret-policy', PlatformVariableSecretPolicy);
