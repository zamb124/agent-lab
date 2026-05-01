/**
 * flows-incoming-policy-modal — выбор incoming_policy ноды (any | all).
 *
 * Тело — две карточки: ANY (нода стартует при первом пришедшем ребре) и
 * ALL (AND-join, нода ждёт завершения всех входящих). Клик по карточке
 * сразу пишет политику в `flows/editor.skillsData.nodes[nodeId]` и
 * закрывает модалку. Кнопок Save/Cancel нет.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { asObject } from '../_helpers/flows-resolvers.js';

const ICON_ANY = html`
    <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
        <path d="m4 13h16a1 1 0 0 0 0-2h-16a1 1 0 0 0 0 2z" fill="currentColor"/>
        <path d="m20 5h-16a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2z" fill="currentColor"/>
        <path d="m4 19h16a1 1 0 0 0 0-2h-16a1 1 0 0 0 0 2z" fill="currentColor"/>
    </svg>
`;

const ICON_ALL = html`
    <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
        <path d="m20 14.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z" fill="currentColor"/>
        <path d="m20 6.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z" fill="currentColor"/>
        <path d="m20 22.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z" fill="currentColor"/>
        <path d="m4 14.3c1.2 0 2.3-1 2.3-2.3s-1.1-2.2-2.3-2.2-2.3 1-2.3 2.3 1.1 2.2 2.3 2.2z" fill="currentColor"/>
        <path d="m19 12.8c.4 0 .8-.3.8-.8s-.3-.8-.8-.8h-7.3v-4.2c0-1.6.7-2.3 2.3-2.3h5c.4 0 .8-.3.8-.8s-.4-.6-.8-.6h-5c-2.4 0-3.8 1.3-3.8 3.8v4.3h-5.2c-.4 0-.8.3-.8.8s.3.8.8.8h5.3v4c0 2.4 1.3 3.8 3.8 3.8h5c.4 0 .8-.3.8-.8s-.3-.8-.8-.8h-5c-1.6 0-2.3-.7-2.3-2.3v-4.3h7.2z" fill="currentColor"/>
    </svg>
`;

export class FlowsIncomingPolicyModal extends PlatformModal {
    static modalKind = 'flows.incoming_policy';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        nodeId: { type: String },
        _policy: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .subtitle {
                margin: 0 0 var(--space-4);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.4;
            }
            .subtitle-id {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                display: block;
                margin-top: var(--space-1);
            }
            .cards {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-3);
                align-items: stretch;
                min-width: 0;
            }
            @media (max-width: 520px) {
                .cards {
                    grid-template-columns: 1fr;
                }
            }
            .card {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-4);
                margin: 0;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                border: 2px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font: inherit;
                text-align: center;
                cursor: pointer;
                transition: border-color 120ms, background 120ms, box-shadow 120ms;
            }
            .card:hover {
                border-color: var(--border-medium);
                background: var(--glass-tint-medium);
            }
            .card[data-selected] {
                border-color: var(--accent);
                background: var(--accent-subtle);
                box-shadow: 0 0 0 1px var(--accent-subtle);
            }
            .card-icon {
                width: 72px;
                height: 72px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
            }
            .card[data-selected] .card-icon { color: var(--accent); }
            .card-title {
                font-size: var(--text-md);
                font-weight: var(--font-semibold);
                min-width: 0;
                width: 100%;
                word-break: break-word;
            }
            .card-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.45;
                min-width: 0;
                width: 100%;
                word-break: break-word;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.nodeId = '';
        this._policy = 'any';
        this._hydrated = false;
        this._editor = this.useOp('flows/editor');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('nodeId') || (changed.has('open') && this.open)) {
            this._hydrated = false;
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.nodeId) {
            const node = this._editor.state?.branchData?.nodes?.[this.nodeId];
            if (node) {
                this._policy = node.incoming_policy === 'all' ? 'all' : 'any';
                this._hydrated = true;
            }
        }
    }

    _displayNodeName() {
        const n = this._editor.state?.branchData?.nodes?.[this.nodeId];
        if (n && typeof n.name === 'string' && n.name.length > 0) {
            return n.name;
        }
        return this.nodeId;
    }

    renderHeader() {
        return html`${this.t('incoming_policy_modal.title')}`;
    }

    renderBody() {
        const showId = this._displayNodeName() !== this.nodeId;
        return html`
            <div>
                <p class="subtitle">
                    ${this.t('incoming_policy_modal.subtitle', { name: this._displayNodeName() })}
                    ${showId
                        ? html`<span class="subtitle-id">${this.nodeId}</span>`
                        : null}
                </p>
            </div>
            <div class="cards">
                <button
                    type="button"
                    class="card"
                    ?data-selected=${this._policy === 'any'}
                    @click=${() => this._pick('any')}
                >
                    <span class="card-icon">${ICON_ANY}</span>
                    <span class="card-title">${this.t('incoming_policy_modal.option_any_title')}</span>
                    <span class="card-desc">${this.t('incoming_policy_modal.option_any_desc')}</span>
                </button>
                <button
                    type="button"
                    class="card"
                    ?data-selected=${this._policy === 'all'}
                    @click=${() => this._pick('all')}
                >
                    <span class="card-icon">${ICON_ALL}</span>
                    <span class="card-title">${this.t('incoming_policy_modal.option_all_title')}</span>
                    <span class="card-desc">${this.t('incoming_policy_modal.option_all_desc')}</span>
                </button>
            </div>
        `;
    }

    renderFooter() {
        return html``;
    }

    _pick(policy) {
        const data = this._editor.state?.branchData;
        if (!data || !this.nodeId) {
            this.close();
            return;
        }
        const nodes = { ...asObject(data.nodes) };
        const node = nodes[this.nodeId];
        if (!node) {
            this.close();
            return;
        }
        nodes[this.nodeId] = { ...node, incoming_policy: policy };
        const next = { ...data, nodes };
        this._editor.updateBranchData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this.close();
    }
}

customElements.define('flows-incoming-policy-modal', FlowsIncomingPolicyModal);
registerModalKind(FlowsIncomingPolicyModal.modalKind, 'flows-incoming-policy-modal');
