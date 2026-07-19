/**
 * <platform-agent-plan> — универсальный checklist AgentPlan (presentational).
 * Props: .plan = { agent_plan_id, title?, steps: [{ step_id, title, status }] }
 */

import { html, css, nothing } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

const STATUS_ICON = {
    pending: 'circle',
    in_progress: 'hourglass-top',
    completed: 'check',
    need_help: 'alert-triangle',
    failed: 'alert-triangle',
};

const KNOWN_STATUSES = new Set(Object.keys(STATUS_ICON));

function _asPlan(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return null;
    }
    const steps = Array.isArray(value.steps) ? value.steps : null;
    if (steps === null || steps.length === 0) {
        return null;
    }
    return value;
}

function _stepStatus(step) {
    const raw = step && typeof step.status === 'string' ? step.status : 'pending';
    return KNOWN_STATUSES.has(raw) ? raw : 'pending';
}

export class PlatformAgentPlan extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        plan: { attribute: false },
        compact: { type: Boolean, reflect: true },
        readonly: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .shell {
                border: 1px solid var(--border-subtle, var(--glass-border-subtle));
                border-radius: var(--radius-lg, 10px);
                background: var(--surface-elevated, var(--glass-solid-subtle));
                overflow: hidden;
            }
            .header {
                display: flex;
                align-items: center;
                gap: var(--space-2, 8px);
                padding: var(--space-3, 12px) var(--space-4, 14px);
                border-bottom: 1px solid var(--border-subtle, var(--glass-border-subtle));
            }
            .header-title {
                font-size: var(--text-sm, 0.875rem);
                font-weight: 600;
                color: var(--text-primary);
                margin: 0;
            }
            .list {
                list-style: none;
                margin: 0;
                padding: var(--space-2, 8px);
            }
            .row {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2, 8px);
                padding: 6px 8px;
                border-radius: var(--radius-md, 8px);
                animation: agent-plan-in 0.22s ease-out both;
            }
            .row:hover {
                background: var(--glass-solid-subtle, rgba(0, 0, 0, 0.03));
            }
            .icon-wrap {
                flex-shrink: 0;
                width: 1.25rem;
                height: 1.25rem;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                margin-top: 1px;
                color: var(--text-muted);
            }
            .row[data-status='completed'] .icon-wrap {
                color: var(--success, #16a34a);
            }
            .row[data-status='in_progress'] .icon-wrap {
                color: var(--accent, #2563eb);
            }
            .row[data-status='need_help'] .icon-wrap {
                color: var(--warning, #ca8a04);
            }
            .row[data-status='failed'] .icon-wrap {
                color: var(--danger, #dc2626);
            }
            .body {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2, 8px);
            }
            .title {
                font-size: var(--text-sm, 0.875rem);
                color: var(--text-primary);
                line-height: 1.35;
                word-break: break-word;
            }
            .row[data-status='completed'] .title {
                color: var(--text-muted);
                text-decoration: line-through;
            }
            .badge {
                flex-shrink: 0;
                font-size: 10px;
                font-weight: 600;
                line-height: 1;
                padding: 3px 6px;
                border-radius: var(--radius-sm, 4px);
                text-transform: lowercase;
                color: var(--text-muted);
                background: var(--surface-muted, rgba(0, 0, 0, 0.06));
            }
            .row[data-status='completed'] .badge {
                color: #166534;
                background: rgba(22, 163, 74, 0.12);
            }
            .row[data-status='in_progress'] .badge {
                color: #1d4ed8;
                background: rgba(37, 99, 235, 0.12);
            }
            .row[data-status='need_help'] .badge {
                color: #a16207;
                background: rgba(202, 138, 4, 0.14);
            }
            .row[data-status='failed'] .badge {
                color: #b91c1c;
                background: rgba(220, 38, 38, 0.12);
            }
            :host([compact]) .header {
                padding: 8px 10px;
            }
            :host([compact]) .list {
                padding: 4px;
            }
            @keyframes agent-plan-in {
                from {
                    opacity: 0;
                    transform: translateY(-4px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            @media (prefers-reduced-motion: reduce) {
                .row {
                    animation: none;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.plan = null;
        this.compact = false;
        this.readonly = true;
    }

    _statusLabel(status) {
        return this.t(`agent_plan.status.${status}`);
    }

    render() {
        const plan = _asPlan(this.plan);
        if (plan === null) {
            return nothing;
        }
        const title =
            typeof plan.title === 'string' && plan.title.trim().length > 0
                ? plan.title.trim()
                : this.t('agent_plan.title');
        const steps = plan.steps;
        return html`
            <div class="shell" role="list" aria-label=${title}>
                <div class="header">
                    <platform-icon name="checklist" size="16"></platform-icon>
                    <h3 class="header-title">${title}</h3>
                </div>
                <ul class="list">
                    ${steps.map((step, index) => {
                        const status = _stepStatus(step);
                        const icon = STATUS_ICON[status];
                        const stepTitle =
                            step && typeof step.title === 'string' ? step.title : '';
                        return html`
                            <li
                                class="row"
                                data-status=${status}
                                role="listitem"
                                style="animation-delay: ${Math.min(index, 8) * 40}ms"
                            >
                                <span class="icon-wrap" aria-hidden="true">
                                    <platform-icon name=${icon} size="16"></platform-icon>
                                </span>
                                <div class="body">
                                    <span class="title">${stepTitle}</span>
                                    <span class="badge">${this._statusLabel(status)}</span>
                                </div>
                            </li>
                        `;
                    })}
                </ul>
            </div>
        `;
    }
}

customElements.define('platform-agent-plan', PlatformAgentPlan);
