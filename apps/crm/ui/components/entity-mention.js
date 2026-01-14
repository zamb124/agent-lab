/**
 * Entity Mention - Highlighted упоминание сущности в тексте
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class EntityMention extends PlatformElement {
    static properties = {
        entityId: { type: String, attribute: 'entity-id' },
        entityType: { type: String, attribute: 'entity-type' },
        _cardOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline;
                position: relative;
            }
            
            .mention {
                background: var(--accent-subtle);
                border-radius: var(--radius-sm);
                padding: 2px 6px;
                cursor: pointer;
                transition: all 0.2s;
                text-decoration: none;
                color: var(--accent);
                font-weight: 500;
            }
            
            .mention:hover {
                background: var(--accent);
                color: white;
            }
            
            .mention.contact {
                background: rgba(59, 130, 246, 0.15);
                color: rgb(59, 130, 246);
            }
            
            .mention.contact:hover {
                background: rgb(59, 130, 246);
                color: white;
            }
            
            .mention.company {
                background: rgba(168, 85, 247, 0.15);
                color: rgb(168, 85, 247);
            }
            
            .mention.company:hover {
                background: rgb(168, 85, 247);
                color: white;
            }
            
            .mention.task {
                background: rgba(34, 197, 94, 0.15);
                color: rgb(34, 197, 94);
            }
            
            .mention.task:hover {
                background: rgb(34, 197, 94);
                color: white;
            }
            
            .card-popup {
                position: absolute;
                bottom: 100%;
                left: 50%;
                transform: translateX(-50%) translateY(-8px);
                z-index: 1000;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.2s;
            }
            
            .card-popup.open {
                opacity: 1;
                pointer-events: all;
            }
            
            .card-content {
                min-width: 250px;
                padding: var(--space-4);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-strong);
            }
            
            .card-arrow {
                position: absolute;
                bottom: -6px;
                left: 50%;
                transform: translateX(-50%);
                width: 12px;
                height: 12px;
                background: var(--glass-solid-strong);
                border-right: 1px solid var(--glass-border-medium);
                border-bottom: 1px solid var(--glass-border-medium);
                transform: translateX(-50%) rotate(45deg);
            }
            
            .card-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-bottom: var(--space-2);
            }
            
            .card-name {
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            
            .card-description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.4;
            }
        `
    ];

    constructor() {
        super();
        this.entityId = '';
        this.entityType = '';
        this._cardOpen = false;
        this._cardData = null;
    }
    
    _getTypeClass() {
        const typeMap = {
            'contact': 'contact',
            'company': 'company',
            'task': 'task',
        };
        return typeMap[this.entityType] || '';
    }
    
    _onMouseEnter() {
        this._cardOpen = true;
    }
    
    _onMouseLeave() {
        this._cardOpen = false;
    }
    
    _onClick() {
        console.log('[EntityMention] Clicked:', this.entityId, this.entityType);
        this.dispatchEvent(new CustomEvent('entity-click', {
            detail: { entityId: this.entityId, entityType: this.entityType },
            bubbles: true,
            composed: true
        }));
    }

    render() {
        const typeClass = this._getTypeClass();
        
        return html`
            <span 
                class="mention ${typeClass}"
                @mouseenter=${this._onMouseEnter}
                @mouseleave=${this._onMouseLeave}
                @click=${this._onClick}
            >
                <slot></slot>
            </span>
            
            <div class="card-popup ${this._cardOpen ? 'open' : ''}">
                <div class="card-content">
                    <div class="card-type">${this.entityType}</div>
                    <div class="card-name">
                        <slot></slot>
                    </div>
                    <div class="card-description">
                        ID: ${this.entityId}
                    </div>
                </div>
                <div class="card-arrow"></div>
            </div>
        `;
    }
}

customElements.define('entity-mention', EntityMention);

