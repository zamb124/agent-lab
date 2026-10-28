/**
 * FlowCard - карточка flow в sidebar
 * Expandable с отображением веток (branches)
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import './branch-item.js';
import { asString } from '../_helpers/flows-resolvers.js';
import { resolveFlowCoverGradient } from '../_helpers/flow-cover-gradients.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowCard extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        flow: { type: Object },
        active: { type: Boolean, reflect: true },
        expanded: { type: Boolean, reflect: true },
        collapsed: { type: Boolean, reflect: true },
    }
    declare flow: Record<string, any> | null;
    declare active: boolean;
    declare expanded: boolean;
    declare collapsed: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        glassStyles,
        css`
            :host {
                display: block;
                --platform-button-icon-size: var(--flows-card-action-size);
            }

            .flow-card {
                border-radius: var(--radius-xl);
                background: transparent;
                border: 1px solid transparent;
                transition: var(--motion-transition-interactive);
                overflow: visible;
            }

            .flow-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--border-subtle);
            }

            .flow-card.expanded {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-subtle);
            }

            .flow-card.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
            }

            .flow-header {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-3);
                padding-right: calc(var(--space-2) + 22px);
                cursor: pointer;
                position: relative;
                transition: padding-right var(--duration-fast) var(--easing-default);
                min-width: 0;
            }

            .flow-card.expanded .flow-header {
                padding-right: 118px;
            }

            @media (hover: hover) and (min-width: 768px) {
                .flow-card:hover .flow-header {
                    padding-right: 118px;
                }
            }

            .flow-avatar {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                font-weight: var(--font-bold);
                font-size: var(--text-sm);
                color: var(--flows-avatar-text);
                flex-shrink: 0;
                position: relative;
                transition: var(--motion-transition-interactive);
            }

            .flow-card:hover .flow-avatar {
                transform: scale(1.05);
                box-shadow: var(--flows-avatar-hover-shadow);
            }

            .employee-avatar-badge {
                position: absolute;
                right: 0;
                bottom: 0;
                width: var(--flows-employee-badge-size);
                height: var(--flows-employee-badge-size);
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                background: var(--glass-solid-strong);
                border: 1.5px solid var(--flows-employee-badge-ring);
                box-shadow: var(--flows-employee-badge-glow);
                color: var(--accent);
                pointer-events: none;
                transform: translate(25%, 25%);
            }

            .flow-info {
                flex: 1;
                min-width: 0;
                overflow: hidden;
            }

            .flow-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                line-height: 1.4;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            .flow-card.active .flow-name {
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .flow-subid {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .flow-meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: 2px;
                min-width: 0;
            }

            .bundle-update-indicator {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--warning);
                box-shadow: var(--flows-bundle-update-shadow);
                flex-shrink: 0;
            }

            .flow-actions {
                display: none;
                gap: var(--space-1);
                position: absolute;
                top: var(--space-2);
                right: 30px;
                z-index: 1;
                align-items: center;
            }

            .flow-card:hover .flow-actions,
            .flow-card.expanded .flow-actions {
                display: flex;
            }

            .expand-icon {
                width: 20px;
                height: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                transition: transform var(--duration-fast);
                position: absolute;
                right: var(--space-2);
                top: 50%;
                transform: translateY(-50%);
            }

            .expand-icon.expanded {
                transform: translateY(-50%) rotate(90deg);
            }

            .flow-details {
                padding: 0 var(--space-4) var(--space-4);
                animation: slideDown var(--duration-normal) var(--easing-default);
            }

            @keyframes slideDown {
                from {
                    opacity: 0;
                    transform: translateY(-8px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .branches-section {
                border-radius: var(--radius-lg);
                padding: var(--space-3);
            }

            .branches-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-2);
            }

            .branches-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
            }

            .branches-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .branches-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2);
                text-align: center;
            }

            :host([collapsed]) {
                display: flex;
                justify-content: center;
                width: 100%;
                min-width: 0;
                overflow: visible;
            }

            :host([collapsed]) .flow-info,
            :host([collapsed]) .flow-actions,
            :host([collapsed]) .expand-icon,
            :host([collapsed]) .flow-details {
                display: none;
            }

            :host([collapsed]) .flow-header {
                width: 40px;
                height: 40px;
                justify-content: center;
                align-items: center;
                gap: 0;
                padding: 0;
                padding-right: 0;
                box-sizing: border-box;
                overflow: visible;
            }

            :host([collapsed]) .flow-avatar {
                width: 36px;
                height: 36px;
                font-size: var(--text-xs);
            }

            :host([collapsed]) .flow-card {
                border-radius: var(--radius-lg);
                box-sizing: border-box;
                width: 44px;
                max-width: 44px;
                margin-inline: auto;
                overflow: visible;
            }

            :host([collapsed]) .flow-card:hover .flow-header,
            :host([collapsed]) .flow-card.expanded .flow-header {
                padding-right: 0;
            }

            @media (max-width: 767px) {
                .flow-actions {
                    display: none;
                }

                .flow-card.expanded .flow-actions {
                    display: flex;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.flow = null;
        this.active = false;
        this.expanded = false;
        this.collapsed = false;
    }

    _getInitials() {
        let name;
        if (this.flow && typeof this.flow.name === 'string' && this.flow.name.length > 0) {
            name = this.flow.name;
        } else if (this.flow && typeof this.flow.flow_id === 'string') {
            name = this.flow.flow_id;
        } else {
            name = '';
        }
        const words = name.split(/[\s_-]+/);
        if (words.length >= 2) {
            const firstWord = words[0];
            const secondWord = words[1];
            if (firstWord === undefined || secondWord === undefined) {
                throw new Error('flow-card: initials words missing');
            }
            return (firstWord.charAt(0) + secondWord.charAt(0)).toUpperCase();
        }
        return name.substring(0, 2).toUpperCase();
    }

    _getCoverGradient() {
        const flowId = asString(this.flow?.flow_id);
        return resolveFlowCoverGradient(flowId);
    }

    _getBranches() {
        if (!this.flow?.branches) return [];
        return Object.entries(this.flow.branches).map(([id, br]: [string, any]) => ({
            id,
            name: br.name,
            description: br.description,
        }));
    }

    _requireFlow(): Record<string, any> {
        const flow = this.flow;
        if (flow === null) {
            throw new Error('flow-card: flow required');
        }
        return flow;
    }

    _emitAction(action: any, e: Event, branchId: any = null) {
        e?.stopPropagation();
        this.emit('flow-action', {
            action,
            flowId: this._requireFlow().flow_id,
            branchId,
        });
    }

    _handleHeaderClick(e: Event) {
        if ((e.target as HTMLElement | null)?.closest('.flow-actions')) return;
        this._emitAction('toggle', e);
    }

    override render(): TemplateResult | typeof nothing {
        if (!this.flow) return nothing;

        const cardClass = [
            'flow-card',
            this.expanded ? 'expanded' : '',
            this.active ? 'active' : '',
        ].filter((part) => part.length > 0).join(' ');

        const expandClass = [
            'expand-icon',
            this.expanded ? 'expanded' : '',
        ].filter((part) => part.length > 0).join(' ');

        const branches = this._getBranches();
        const chatTitle = this.t('flow_card.open_chat_title');
        const editTitle = this.t('flow_card.edit_title');
        const deleteTitle = this.t('flow_card.delete_title');
        const addBranchTitle = this.t('flow_card.add_branch_title');
        const employeeEnabled =
            this.flow.employee &&
            typeof this.flow.employee === 'object' &&
            (this.flow.employee as Record<string, any>).enabled === true;
        const employeeBadgeTitle = this.t('flow_card.employee_badge_title');

        return html`
            <div class=${cardClass} data-flow-id=${this.flow.flow_id}>
                <div class="flow-header" @click=${this._handleHeaderClick}>
                    <div
                        class="flow-avatar"
                        style="background: ${this._getCoverGradient()}"
                        ?data-employee=${employeeEnabled}
                    >
                        ${this._getInitials()}
                        ${employeeEnabled
                            ? html`<span class="employee-avatar-badge" title=${employeeBadgeTitle}>
                                  <platform-icon name="ai" size="10"></platform-icon>
                              </span>`
                            : ''}
                    </div>
                    <div class="flow-info">
                        <div class="flow-name">${typeof this.flow.name === 'string' && this.flow.name.length > 0 ? this.flow.name : this.flow.flow_id}</div>
                        <div class="flow-meta">
                            <div class="flow-subid">${this.flow.flow_id}</div>
                            ${this.flow.has_bundle_update
                                ? html`<span
                                    class="bundle-update-indicator"
                                    title=${this.t('flow_card.bundle_update_available')}
                                ></span>`
                                : ''}
                        </div>
                    </div>
                    <div class="flow-actions">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${chatTitle}
                            data-action="open-chat"
                            @click=${(e: Event) => this._emitAction('chat', e)}
                        >
                            <platform-icon name="chat" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${editTitle}
                            data-action="edit-flow"
                            @click=${(e: Event) => this._emitAction('edit', e)}
                        >
                            <platform-icon name="edit" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${deleteTitle}
                            data-action="delete-flow"
                            @click=${(e: Event) => this._emitAction('delete', e)}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </platform-button>
                    </div>
                    <div class=${expandClass}>
                        <platform-icon name="chevron-right" size="14"></platform-icon>
                    </div>
                </div>

                ${this.expanded ? html`
                    <div class="flow-details">
                        <div class="branches-section glass-subtle">
                            <div class="branches-header">
                                <span class="branches-title">${this.t('flow_card.branches_title')}</span>
                                <platform-button
                                    variant="ghost"
                                    icon-only
                                    density="dense"
                                    aria-label=${addBranchTitle}
                                    @click=${(e: CustomEvent) => this._emitAction('create-branch', e)}
                                >
                                    <platform-icon name="plus" size="12"></platform-icon>
                                </platform-button>
                            </div>

                            ${branches.length > 0 ? html`
                                <div class="branches-list">
                                    ${branches.map((br) => html`
                                        <branch-item
                                            .branch=${br}
                                            .flowId=${this._requireFlow().flow_id}
                                            @branch-action=${(e: CustomEvent) => this._emitAction(e.detail.action, e, br.id)}
                                        ></branch-item>
                                    `)}
                                </div>
                            ` : html`
                                <div class="branches-empty">${this.t('flow_card.no_branches')}</div>
                            `}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('flow-card', FlowCard);
