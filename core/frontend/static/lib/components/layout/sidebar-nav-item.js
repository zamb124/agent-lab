/**
 * SidebarNavItem - элемент навигации для sidebar
 * Поддержка collapsed mode, expandable content, badges, actions
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../../platform-element/index.js';
import { sidebarNavItemStyles } from '../../styles/shared/sidebar.styles.js';
import '../platform-icon.js';

export class SidebarNavItem extends PlatformElement {
    static properties = {
        icon: { type: String },
        iconGradient: { type: String, attribute: 'icon-gradient' },
        label: { type: String },
        badge: { type: String },
        active: { type: Boolean, reflect: true },
        expandable: { type: Boolean },
        expanded: { type: Boolean, reflect: true },
        href: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        sidebarNavItemStyles,
        css`
            :host {
                display: block;
            }

            .nav-item-content {
                padding: var(--space-3) var(--space-4);
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

            :host([collapsed]) .nav-item-content {
                display: none;
            }
        `
    ];

    constructor() {
        super();
        this.icon = '';
        this.iconGradient = '';
        this.label = '';
        this.badge = '';
        this.active = false;
        this.expandable = false;
        this.expanded = false;
        this.href = '';
    }

    _handleClick(e) {
        if (this.expandable) {
            e.preventDefault();
            this.expanded = !this.expanded;
            this.emit('toggle-expand', { expanded: this.expanded });
        }
        
        this.emit('nav-click', { 
            label: this.label,
            href: this.href,
        });
    }

    _getIconClasses() {
        const classes = { 'nav-item-icon': true };
        
        if (this.iconGradient) {
            classes[`gradient-${this.iconGradient}`] = true;
        }
        
        return classes;
    }

    render() {
        const itemClasses = {
            'nav-item': true,
            'active': this.active,
        };

        const expandClasses = {
            'nav-item-expand': true,
            'expanded': this.expanded,
        };

        const Tag = this.href ? 'a' : 'button';

        return html`
            <${Tag} 
                class=${classMap(itemClasses)}
                href=${this.href || undefined}
                @click=${this._handleClick}
            >
                ${this.icon ? html`
                    <div class=${classMap(this._getIconClasses())}>
                        <platform-icon name="${this.icon}" size="18"></platform-icon>
                    </div>
                ` : ''}
                
                <span class="nav-item-label">${this.label}</span>
                
                ${this.badge ? html`
                    <span class="nav-item-badge">${this.badge}</span>
                ` : ''}
                
                <div class="nav-item-actions">
                    <slot name="actions"></slot>
                </div>
                
                ${this.expandable ? html`
                    <div class=${classMap(expandClasses)}>
                        <platform-icon name="chevron-right" size="14"></platform-icon>
                    </div>
                ` : ''}
            </${Tag}>
            
            ${this.expandable && this.expanded ? html`
                <div class="nav-item-content">
                    <slot></slot>
                </div>
            ` : ''}
        `;
    }
}

customElements.define('sidebar-nav-item', SidebarNavItem);
