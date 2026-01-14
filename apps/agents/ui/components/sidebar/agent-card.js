/**
 * AgentCard - карточка агента в sidebar
 * Expandable с отображением skills
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import './skill-item.js';

export class AgentCard extends PlatformElement {
    static properties = {
        agent: { type: Object },
        active: { type: Boolean, reflect: true },
        expanded: { type: Boolean, reflect: true },
        collapsed: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .agent-card {
                border-radius: var(--radius-xl);
                background: transparent;
                border: 1px solid transparent;
                transition: all var(--duration-normal) var(--easing-default);
                overflow: hidden;
            }

            .agent-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
            }

            .agent-card.expanded {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-subtle);
            }

            .agent-card.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
            }

            .agent-header {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                cursor: pointer;
            }

            .agent-avatar {
                width: 42px;
                height: 42px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                font-weight: var(--font-bold);
                font-size: var(--text-sm);
                color: white;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
                flex-shrink: 0;
                transition: all var(--duration-normal) var(--easing-default);
            }

            .agent-card:hover .agent-avatar {
                transform: scale(1.05);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            }

            .agent-info {
                flex: 1;
                min-width: 0;
            }

            .agent-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                line-height: 1.4;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            .agent-card.active .agent-name {
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .agent-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
            }

            .agent-actions {
                display: none;
                gap: var(--space-1);
            }

            .agent-card:hover .agent-actions,
            .agent-card.expanded .agent-actions {
                display: flex;
            }

            .action-btn {
                width: 26px;
                height: 26px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: none;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .action-btn platform-icon {
                pointer-events: none;
            }

            .action-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }

            .action-btn.chat:hover {
                color: var(--accent);
            }

            .action-btn.danger:hover {
                background: var(--error-bg);
                color: var(--error);
            }

            .expand-icon {
                width: 20px;
                height: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                transition: transform var(--duration-fast);
            }

            .expand-icon.expanded {
                transform: rotate(90deg);
            }

            .agent-details {
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

            .skills-section {
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
            }

            .skills-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-2);
            }

            .skills-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
            }

            .skill-add-btn {
                width: 22px;
                height: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: none;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .skill-add-btn platform-icon {
                pointer-events: none;
            }

            .skill-add-btn:hover {
                background: var(--accent-subtle);
                color: var(--accent);
            }

            .skills-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .skills-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2);
                text-align: center;
            }

            /* Collapsed mode */
            :host([collapsed]) .agent-info,
            :host([collapsed]) .agent-actions,
            :host([collapsed]) .expand-icon,
            :host([collapsed]) .agent-details {
                display: none;
            }

            :host([collapsed]) .agent-header {
                justify-content: center;
                padding: var(--space-3);
            }

            :host([collapsed]) .agent-card {
                border-radius: var(--radius-lg);
            }

            @media (max-width: 767px) {
                .agent-actions {
                    display: none;
                }

                .agent-card.expanded .agent-actions {
                    display: flex;
                }
            }
        `
    ];

    constructor() {
        super();
        this.agent = null;
        this.active = false;
        this.expanded = false;
        this.collapsed = false;
    }

    _getInitials() {
        const name = this.agent?.name || this.agent?.agent_id || '';
        const words = name.split(/[\s_-]+/);
        if (words.length >= 2) {
            return (words[0].charAt(0) + words[1].charAt(0)).toUpperCase();
        }
        return name.substring(0, 2).toUpperCase();
    }

    _getColor() {
        const colors = [
            'linear-gradient(135deg, #10b981 0%, #06b6d4 100%)',
            'linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)',
            'linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)',
            'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
            'linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%)',
            'linear-gradient(135deg, #84cc16 0%, #10b981 100%)',
            'linear-gradient(135deg, #f97316 0%, #f59e0b 100%)',
            'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
        ];
        const hash = (this.agent?.agent_id || '').split('').reduce((a, b) => a + b.charCodeAt(0), 0);
        return colors[hash % colors.length];
    }

    _getSkills() {
        if (!this.agent?.skills) return [];
        return Object.entries(this.agent.skills).map(([id, skill]) => ({
            id,
            name: skill.name,
            description: skill.description,
        }));
    }

    _emitAction(action, e, skillId = null) {
        e?.stopPropagation();
        this.emit('agent-action', {
            action,
            agentId: this.agent.agent_id,
            skillId,
        });
    }

    _handleHeaderClick(e) {
        if (e.target.closest('.agent-actions')) return;
        this._emitAction('toggle', e);
    }

    render() {
        if (!this.agent) return '';

        const cardClasses = {
            'agent-card': true,
            'expanded': this.expanded,
            'active': this.active,
        };

        const expandClasses = {
            'expand-icon': true,
            'expanded': this.expanded,
        };

        const skills = this._getSkills();

        return html`
            <div class=${classMap(cardClasses)}>
                <div class="agent-header" @click=${this._handleHeaderClick}>
                    <div 
                        class="agent-avatar" 
                        style="background: ${this._getColor()}"
                    >
                        ${this._getInitials()}
                    </div>
                    <div class="agent-info">
                        <div class="agent-name">${this.agent.name || this.agent.agent_id}</div>
                        <div class="agent-type">${this.agent.agent_id}</div>
                    </div>
                    <div class="agent-actions">
                        <button 
                            class="action-btn chat" 
                            @click=${(e) => this._emitAction('chat', e)}
                            title="Открыть чат"
                        >
                            <platform-icon name="chat" size="14"></platform-icon>
                        </button>
                        <button 
                            class="action-btn" 
                            @click=${(e) => this._emitAction('edit', e)}
                            title="Редактировать"
                        >
                            <platform-icon name="edit" size="14"></platform-icon>
                        </button>
                        <button 
                            class="action-btn danger" 
                            @click=${(e) => this._emitAction('delete', e)}
                            title="Удалить"
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </button>
                    </div>
                    <div class=${classMap(expandClasses)}>
                        <platform-icon name="chevron-right" size="14"></platform-icon>
                    </div>
                </div>

                ${this.expanded ? html`
                    <div class="agent-details">
                        <div class="skills-section">
                            <div class="skills-header">
                                <span class="skills-title">Skills</span>
                                <button 
                                    class="skill-add-btn" 
                                    @click=${(e) => this._emitAction('create-skill', e)}
                                    title="Добавить skill"
                                >
                                    <platform-icon name="plus" size="12"></platform-icon>
                                </button>
                            </div>

                            ${skills.length > 0 ? html`
                                <div class="skills-list">
                                    ${skills.map(skill => html`
                                        <skill-item
                                            .skill=${skill}
                                            .agentId=${this.agent.agent_id}
                                            @skill-action=${(e) => this._emitAction(e.detail.action, e, skill.id)}
                                        ></skill-item>
                                    `)}
                                </div>
                            ` : html`
                                <div class="skills-empty">Нет skills</div>
                            `}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('agent-card', AgentCard);
