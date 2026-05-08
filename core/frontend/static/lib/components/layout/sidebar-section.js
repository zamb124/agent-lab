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
        customHeader: { type: Boolean, reflect: true, attribute: 'custom-header' },
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

            .section-header.section-header--custom {
                justify-content: stretch;
                padding: var(--space-2) 0;
            }
        `
    ];

    constructor() {
        super();
        this.title = '';
        this.icon = '';
        this.collapsed = false;
        this.customHeader = false;
    }

    render() {
        const header = this.customHeader
            ? html`
                <div class="section-header section-header--custom">
                    <slot name="header"></slot>
                </div>
            `
            : html`
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
            `;
        return html`
            <div class="section">
                ${header}
                <div class="section-content">
                    <slot></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('sidebar-section', SidebarSection);
