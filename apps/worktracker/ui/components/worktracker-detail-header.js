/**
 * WorktrackerDetailHeader — task detail toolbar (id chip + actions).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { TERMINAL_STATES, queueUnclaimed } from '../utils/work-item-detail-shared.js';
import './worktracker-icon-action.js';
import '@platform/lib/components/platform-icon.js';

export class WorktrackerDetailHeader extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        item: { attribute: false },
        showBack: { type: Boolean, attribute: 'show-back' },
        showProperties: { type: Boolean, attribute: 'show-properties' },
        showLifecycleActions: { type: Boolean, attribute: 'show-lifecycle-actions' },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-height: 40px;
                flex-shrink: 0;
            }
            .spacer {
                flex: 1;
                min-width: 0;
            }
            .actions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
            }
            .back-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                border: var(--worktracker-divider);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                flex-shrink: 0;
            }
            .back-btn:hover {
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
            }
        `,
    ];

    constructor() {
        super();
        this.item = null;
        this.showBack = false;
        this.showProperties = false;
        this.showLifecycleActions = true;
    }

    render() {
        const item = this.item;
        const isTerminal = item && TERMINAL_STATES.has(item.state);
        const showClaim = item && queueUnclaimed(item);

        return html`
            ${this.showBack ? html`
                <button
                    type="button"
                    class="back-btn"
                    aria-label=${this.t('detail_page.back')}
                    @click=${() => this.emit('wt-back', null)}
                >
                    <platform-icon name="arrow-left" size="18"></platform-icon>
                </button>
            ` : nothing}
            <div class="spacer"></div>
            <div class="actions">
                ${this.showProperties ? html`
                    <worktracker-icon-action
                        icon="settings"
                        title=${this.t('detail_page.open_properties')}
                        @action=${() => this.emit('wt-open-properties', null)}
                    ></worktracker-icon-action>
                ` : nothing}
                ${showClaim ? html`
                    <worktracker-icon-action
                        icon="user-plus"
                        title=${this.t('detail_panel.claim')}
                        @action=${() => this.emit('wt-claim', null)}
                    ></worktracker-icon-action>
                ` : nothing}
                ${this.showLifecycleActions && item && !isTerminal ? html`
                    <worktracker-icon-action
                        icon="check"
                        title=${this.t('detail_panel.complete')}
                        @action=${() => this.emit('wt-complete', null)}
                    ></worktracker-icon-action>
                    <worktracker-icon-action
                        icon="close"
                        title=${this.t('detail_panel.cancel')}
                        @action=${() => this.emit('wt-cancel', null)}
                    ></worktracker-icon-action>
                ` : nothing}
                <slot name="actions"></slot>
            </div>
        `;
    }
}

customElements.define('worktracker-detail-header', WorktrackerDetailHeader);
