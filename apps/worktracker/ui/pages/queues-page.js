/**
 * QueuesPage — очереди задач (операторские и общие).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/worktracker-icon-action.js';

export class WorktrackerQueuesPage extends PlatformPage {
    static i18nNamespace = 'worktracker';

    static properties = {
        _name: { state: true },
        _slug: { state: true },
        _showCreate: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        buttonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
                width: 100%;
            }
            .page-title-inline {
                font-size: var(--text-2xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                letter-spacing: var(--tracking-tight);
            }
            .create-card {
                margin-bottom: var(--space-5);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
            }
            .create-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            }
            .create-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                margin-top: var(--space-4);
            }
            .queue-list {
                display: flex;
                flex-direction: column;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
                background: var(--glass-tint-subtle);
            }
            .queue-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                padding: var(--space-3) var(--space-4);
                border: 0;
                border-bottom: 1px solid var(--glass-border-subtle);
                background: transparent;
                color: inherit;
                text-align: left;
                cursor: pointer;
                transition: background 120ms ease;
            }
            .queue-row:last-child {
                border-bottom: 0;
            }
            .queue-row:hover {
                background: var(--glass-tint-medium);
            }
            .queue-icon {
                flex-shrink: 0;
                width: 36px;
                height: 36px;
                border-radius: var(--radius-md);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .queue-meta {
                flex: 1;
                min-width: 0;
            }
            .queue-name {
                display: block;
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .queue-slug {
                display: block;
                margin-top: 2px;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-family: var(--font-mono, ui-monospace, monospace);
            }
            .empty {
                padding: var(--space-8) var(--space-4);
                color: var(--text-tertiary);
                text-align: center;
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this._name = '';
        this._slug = '';
        this._showCreate = false;
        this._queues = this.useResource('worktracker/work_queues');
    }

    connectedCallback() {
        super.connectedCallback();
        this._queues.load({});
    }

    _openQueue(workQueueId) {
        this.navigate('queue_detail', { workQueueId });
    }

    _toggleCreate() {
        this._showCreate = !this._showCreate;
        if (!this._showCreate) {
            this._name = '';
            this._slug = '';
        }
    }

    _create() {
        const name = this._name.trim();
        const slug = this._slug.trim();
        if (!name || !slug) {
            return;
        }
        this._queues.create({ name, slug });
        this._name = '';
        this._slug = '';
        this._showCreate = false;
    }

    render() {
        const queues = this._queues.items || [];
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header dense actions-overflow="visible">
                <span slot="leading" class="page-title-inline">${this.t('queues_page.title')}</span>
                <worktracker-icon-action
                    slot="actions"
                    icon="plus"
                    .title=${this.t('queues_page.create')}
                    ?active=${this._showCreate}
                    @action=${() => this._toggleCreate()}
                ></worktracker-icon-action>
            </page-header>
            ${this._showCreate ? html`
                <section class="create-card">
                    <div class="create-grid">
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('queues_page.label_name')}
                            .value=${this._name}
                            @change=${(e) => {
                                this._name = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                            }}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('queues_page.label_slug')}
                            .value=${this._slug}
                            @change=${(e) => {
                                this._slug = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                            }}
                        ></platform-field>
                    </div>
                    <div class="create-actions">
                        <button type="button" class="btn btn-ghost btn-sm" @click=${() => this._toggleCreate()}>
                            ${this.t('work_item_create_modal.cancel')}
                        </button>
                        <button type="button" class="btn btn-primary btn-sm" @click=${() => this._create()}>
                            ${this.t('queues_page.create')}
                        </button>
                    </div>
                </section>
            ` : ''}
            ${queues.length > 0 ? html`
                <div class="queue-list">
                    ${queues.map((q) => html`
                        <button type="button" class="queue-row" @click=${() => this._openQueue(q.work_queue_id)}>
                            <span class="queue-icon">
                                <platform-icon name="layers" size="18"></platform-icon>
                            </span>
                            <span class="queue-meta">
                                <span class="queue-name">${q.name}</span>
                                <span class="queue-slug">${q.work_queue_slug}</span>
                            </span>
                            <platform-icon name="chevron-right" size="16"></platform-icon>
                        </button>
                    `)}
                </div>
            ` : html`<div class="empty">${this.t('queues_page.empty')}</div>`}
        `;
    }
}

customElements.define('worktracker-queues-page', WorktrackerQueuesPage);
