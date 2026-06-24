/**
 * WorkItemDetailPage — полноценная страница задачи.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { readWorkItemFromParam } from '@platform/lib/utils/work-item-deeplink.js';
import {
    truncateWorkItemId,
    workItemFromEventPayload,
} from '../utils/work-item-detail-shared.js';
import {
    WORK_ITEM_EVENTS,
    WORK_ITEM_MUTATION_SUCCEEDED,
} from '../events/resources/work-items.resource.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/work-item-detail-editor.js';
import '../components/worktracker-detail-header.js';
import '../components/sheets/worktracker-task-properties-sheet.js';

const VALID_FROM_ROUTES = new Set(['inbox', 'my', 'board', 'queues']);

export class WorktrackerWorkItemDetailPage extends PlatformPage {
    static i18nNamespace = 'worktracker';

    static properties = {
        workItemId: { type: String, attribute: 'work-item-id' },
        _isMobile: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                min-width: 0;
                width: 100%;
                height: 100%;
            }
            .shell {
                display: flex;
                flex-direction: column;
                flex: 1 1 auto;
                min-height: 0;
                min-width: 0;
                overflow: visible;
                width: 100%;
                max-width: none;
                margin: 0;
                padding: var(--space-4) var(--space-5);
                box-sizing: border-box;
                gap: var(--space-3);
            }
            .breadcrumbs-wrap {
                flex-shrink: 0;
            }
            .header-wrap {
                flex-shrink: 0;
            }
            .body {
                flex: 1 1 auto;
                min-height: 0;
                min-width: 0;
                overflow: visible;
                width: 100%;
            }
            .body work-item-detail-editor {
                width: 100%;
                min-width: 0;
            }
            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-8);
                color: var(--text-secondary);
                text-align: center;
            }
            @media (max-width: 767px) {
                .breadcrumbs-wrap {
                    display: none;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.workItemId = '';
        this._isMobile = false;
        this._workItems = this.useResource('worktracker/work_items');
        this._claimOp = this.useOp('worktracker/work_item_claim');
        this._completeOp = this.useOp('worktracker/work_item_complete');
        this._cancelOp = this.useOp('worktracker/work_item_cancel');
        this._onMqlChange = this._onMqlChange.bind(this);

        const syncItem = (event) => {
            const item = workItemFromEventPayload(event.payload);
            if (!item || item.work_item_id !== this.workItemId) {
                return;
            }
            this.requestUpdate();
        };
        this.useEvent(this._workItems.resource.events.ITEM_LOADED, syncItem);
        this.useEvent(this._workItems.resource.events.UPDATED, syncItem);
        for (const eventType of WORK_ITEM_MUTATION_SUCCEEDED) {
            this.useEvent(eventType, syncItem);
        }
        for (const eventType of WORK_ITEM_EVENTS) {
            this.useEvent(eventType, syncItem);
        }
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._isMobile = this._mql.matches;
            this._mql.addEventListener('change', this._onMqlChange);
        }
        if (typeof this.workItemId === 'string' && this.workItemId.length > 0) {
            this._workItems.get(this.workItemId);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._mql) {
            this._mql.removeEventListener('change', this._onMqlChange);
        }
    }

    _onMqlChange(event) {
        this._isMobile = event.matches;
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('workItemId') && typeof this.workItemId === 'string' && this.workItemId.length > 0) {
            this._workItems.get(this.workItemId);
        }
    }

    _item() {
        if (!this.workItemId) {
            return null;
        }
        const cached = this._workItems.byId[this.workItemId];
        if (cached && typeof cached === 'object') {
            return cached;
        }
        return null;
    }

    _fromRouteKey() {
        if (typeof window === 'undefined' || typeof window.location === 'undefined') {
            return 'inbox';
        }
        const from = readWorkItemFromParam(window.location);
        if (from.length > 0 && VALID_FROM_ROUTES.has(from)) {
            return from;
        }
        return 'inbox';
    }

    _back() {
        if (typeof window !== 'undefined' && window.history.length > 1) {
            window.history.back();
            return;
        }
        this.navigate(this._fromRouteKey());
    }

    _openProperties() {
        this.openBottomSheet('worktracker.task_properties', { workItemId: this.workItemId });
    }

    render() {
        if (typeof this.workItemId !== 'string' || this.workItemId.length === 0) {
            return html`
                <div class="center">
                    <platform-icon name="info" size="32"></platform-icon>
                    <p>${this.t('detail_page.no_id')}</p>
                </div>
            `;
        }

        const item = this._item();
        const loading = !item && this._workItems.isBusy(this.workItemId);
        const titleLabel = item && typeof item.title === 'string' && item.title.length > 0
            ? item.title
            : truncateWorkItemId(this.workItemId);

        if (loading) {
            return html`
                <div class="center">
                    <glass-spinner size="lg"></glass-spinner>
                </div>
            `;
        }

        if (!item) {
            return html`
                <div class="center">
                    <platform-icon name="info" size="32"></platform-icon>
                    <h2>${this.t('detail_page.not_found')}</h2>
                </div>
            `;
        }

        return html`
            <div class="shell">
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${titleLabel}></platform-breadcrumbs>
                </div>
                ${this._isMobile ? html`
                    <div class="header-wrap">
                        <worktracker-detail-header
                            .item=${item}
                            show-back
                            show-properties
                            ?show-lifecycle-actions=${false}
                            @wt-back=${() => this._back()}
                            @wt-open-properties=${() => this._openProperties()}
                            @wt-claim=${() => this._claimOp.run({ work_item_id: this.workItemId })}
                            @wt-complete=${() => this._completeOp.run({ work_item_id: this.workItemId, resolution_text: '' })}
                            @wt-cancel=${() => this._cancelOp.run({ work_item_id: this.workItemId })}
                        ></worktracker-detail-header>
                    </div>
                ` : nothing}
                <div class="body">
                    <work-item-detail-editor
                        layout="page"
                        work-item-id=${this.workItemId}
                        active
                    ></work-item-detail-editor>
                </div>
            </div>
        `;
    }
}

customElements.define('worktracker-work-item-detail-page', WorktrackerWorkItemDetailPage);
