/**
 * flows-incoming-policy-modal — выбор incoming_policy ноды (any | all).
 *
 * Тело — две карточки: ANY (нода стартует при первом пришедшем ребре) и
 * ALL (AND-слияние, нода ждёт завершения всех входящих). Клик по карточке
 * сразу пишет политику в `flows/editor.skillsData.nodes[nodeId]` и
 * закрывает модалку. Кнопок Save/Cancel нет.
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-picker-card.js';
import { asObject } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

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

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        nodeId: { type: String },
        _policy: { state: true },
        _hydrated: { state: true },
    }
    declare nodeId: string;
    declare _policy: string;
    declare _hydrated: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
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
            platform-picker-card {
                min-width: 0;
            }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;

    constructor() {
        super();
        this.size = 'lg';
        this.nodeId = '';
        this._policy = 'any';
        this._hydrated = false;
        this._editor = this.useOp('flows/editor');
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('nodeId') || (changed.has('open') && this.open)) {
            this._hydrated = false;
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (!this._hydrated && this.nodeId) {
            const node = (this._editor.state as Record<string, any>)?.branchData?.nodes?.[this.nodeId];
            if (node) {
                this._policy = node.incoming_policy === 'all' ? 'all' : 'any';
                this._hydrated = true;
            }
        }
    }

    _displayNodeName() {
        const n = (this._editor.state as Record<string, any>)?.branchData?.nodes?.[this.nodeId];
        if (n && typeof n.name === 'string' && n.name.length > 0) {
            return n.name;
        }
        return this.nodeId;
    }

    override renderHeader() {
        return html`${this.t('incoming_policy_modal.title')}`;
    }

    override renderBody() {
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
                <platform-picker-card
                    value="any"
                    .selected=${this._policy === 'any'}
                    .title=${this.t('incoming_policy_modal.option_any_title')}
                    .subtitle=${this.t('incoming_policy_modal.option_any_desc')}
                    @select=${() => this._pick('any')}
                >
                    <span slot="icon">${ICON_ANY}</span>
                </platform-picker-card>
                <platform-picker-card
                    value="all"
                    .selected=${this._policy === 'all'}
                    .title=${this.t('incoming_policy_modal.option_all_title')}
                    .subtitle=${this.t('incoming_policy_modal.option_all_desc')}
                    @select=${() => this._pick('all')}
                >
                    <span slot="icon">${ICON_ALL}</span>
                </platform-picker-card>
            </div>
        `;
    }

    override renderFooter() {
        return html``;
    }

    _pick(policy: any) {
        const data = this._editor.state?.branchData;
        if (!data || !this.nodeId) {
            this.close();
            return;
        }
        const nodes = { ...asObject((data as Record<string, any>).nodes) };
        const node = nodes[this.nodeId];
        if (!node) {
            this.close();
            return;
        }
        nodes[this.nodeId] = { ...node, incoming_policy: policy };
        const next = { ...data, nodes };
        (this._editor.updateBranchData({ data: next }) as any);
        (this._editor.pushHistory({ snapshot: next }) as any);
        (this._editor.setDirty({ dirty: true }) as any);
        this.close();
    }
}

customElements.define('flows-incoming-policy-modal', FlowsIncomingPolicyModal);
registerModalKind(FlowsIncomingPolicyModal.modalKind, 'flows-incoming-policy-modal');
