/**
 * Progressive-disclosure explainer for Agent Skills (Index → Body → Tools/Refs).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

export class FlowsAgentSkillsHowItWorks extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        compact: { type: Boolean, reflect: true },
        showActions: { type: Boolean, attribute: 'show-actions' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .title {
                margin: 0;
                font-size: var(--text-lg);
                font-weight: 600;
                color: var(--text-primary);
            }
            .subtitle {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.45;
                max-width: 42rem;
            }
            .steps {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
            }
            .step {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                background: var(--bg-elevated);
                border: 1px solid var(--border-subtle);
                min-width: 0;
            }
            .step-num {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border-radius: var(--radius-full, 999px);
                background: var(--accent-muted, var(--bg-surface));
                color: var(--accent);
                font-size: var(--text-xs);
                font-weight: 700;
            }
            .step-title {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
            }
            .step-text {
                margin: 0;
                font-size: var(--text-xs);
                line-height: 1.4;
                color: var(--text-secondary);
            }
            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            :host([compact]) .wrap {
                gap: var(--space-2);
            }
            :host([compact]) .steps {
                grid-template-columns: 1fr;
                gap: var(--space-2);
            }
            :host([compact]) .step {
                flex-direction: row;
                align-items: flex-start;
                padding: var(--space-3);
                gap: var(--space-3);
            }
            :host([compact]) .step-body {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }
            :host([compact]) .title {
                font-size: var(--text-sm);
            }
            :host([compact]) .subtitle {
                display: none;
            }
            @media (max-width: 900px) {
                .steps {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.compact = false;
        this.showActions = false;
    }

    _emit(action) {
        this.emit('agent-skills-action', { action });
    }

    render() {
        const steps = [
            {
                titleKey: 'agent_skills.how_step1_title',
                textKey: 'agent_skills.how_step1_text',
            },
            {
                titleKey: 'agent_skills.how_step2_title',
                textKey: 'agent_skills.how_step2_text',
            },
            {
                titleKey: 'agent_skills.how_step3_title',
                textKey: 'agent_skills.how_step3_text',
            },
        ];
        return html`
            <div class="wrap">
                <h2 class="title">${this.t('agent_skills.how_title')}</h2>
                <p class="subtitle">${this.t('agent_skills.how_subtitle')}</p>
                <div class="steps">
                    ${steps.map((step, index) => html`
                        <div class="step">
                            <span class="step-num">${index + 1}</span>
                            <div class="step-body">
                                <p class="step-title">${this.t(step.titleKey)}</p>
                                <p class="step-text">${this.t(step.textKey)}</p>
                            </div>
                        </div>
                    `)}
                </div>
                ${this.showActions
                    ? html`
                        <div class="actions">
                            <platform-button variant="primary" density="compact" @click=${() => this._emit('create')}>
                                <platform-icon name="plus" size="16"></platform-icon>
                                ${this.t('agent_skills.action_create')}
                            </platform-button>
                            <platform-button variant="secondary" density="compact" @click=${() => this._emit('import')}>
                                <platform-icon name="upload" size="16"></platform-icon>
                                ${this.t('agent_skills.action_import')}
                            </platform-button>
                            <platform-button variant="ghost" density="compact" @click=${() => this._emit('example')}>
                                <platform-icon name="sparkles" size="16"></platform-icon>
                                ${this.t('agent_skills.action_open_example')}
                            </platform-button>
                        </div>
                    `
                    : ''}
            </div>
        `;
    }
}

customElements.define('flows-agent-skills-how-it-works', FlowsAgentSkillsHowItWorks);
