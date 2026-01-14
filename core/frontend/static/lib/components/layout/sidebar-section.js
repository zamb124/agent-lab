/**
 * SidebarSection - секция с заголовком для sidebar
 * Поддержка collapsed mode, action buttons
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { sidebarSectionStyles } from '../../styles/shared/sidebar.styles.js';
import '../platform-icon.js';

export class SidebarSection extends PlatformElement {
    static properties = {
        title: { type: String },
        icon: { type: String },
        collapsed: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        sidebarSectionStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                margin-bottom: var(--space-4);
            }

            :host([collapsed]) .section-header {
                display: none;
            }
        `
    ];

    constructor() {
        super();
        this.title = '';
        this.icon = '';
        this.collapsed = false;
    }

    render() {
        return html`
            <div class="section">
                <div class="section-header">
                    <div class="section-title">
                        ${this.icon ? html`
                            <platform-icon name="${this.icon}" size="14"></platform-icon>
                        ` : ''}
                        <span>${this.title}</span>
                    </div>
                    <div class="section-actions">
                        <slot name="actions"></slot>
                    </div>
                </div>
                <div class="section-content">
                    <slot></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('sidebar-section', SidebarSection);
