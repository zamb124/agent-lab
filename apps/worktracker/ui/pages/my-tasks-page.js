/**
 * MyTasksPage — задачи текущего пользователя.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import '../components/worktracker-work-item-card.js';
import '../components/worktracker-icon-action.js';
import '../components/worktracker-list-section.js';
import '../components/worktracker-page-header.js';
import '@platform/lib/components/platform-icon.js';

export class WorktrackerMyTasksPage extends PlatformPage {
    static i18nNamespace = 'worktracker';

    static styles = [
        PlatformPage.styles,
        worktrackerSurfacesStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this._workItems = this.useResource('worktracker/work_items');
        this._userSel = this.select((s) => s.auth.user);
        this.useEvent(this._workItems.resource.events.CREATED, () => {
            const user = this._userSel.value;
            if (!user || typeof user.user_id !== 'string' || user.user_id.length === 0) {
                throw new Error('WorktrackerMyTasksPage: auth user required');
            }
            this._workItems.load({ assignee_user_id: user.user_id, exclude_terminal: true });
        });
    }

    connectedCallback() {
        super.connectedCallback();
        const user = this._userSel.value;
        if (!user || typeof user.user_id !== 'string' || user.user_id.length === 0) {
            throw new Error('WorktrackerMyTasksPage: auth user required');
        }
        this._workItems.load({ assignee_user_id: user.user_id, exclude_terminal: true });
    }

    _reloadList() {
        const user = this._userSel.value;
        if (!user || typeof user.user_id !== 'string' || user.user_id.length === 0) {
            throw new Error('WorktrackerMyTasksPage: auth user required');
        }
        this._workItems.load({ assignee_user_id: user.user_id, exclude_terminal: true });
    }

    _openCreateTask() {
        this.openModal('worktracker.work_item_create', {});
    }

    render() {
        const items = this._workItems.items || [];
        return html`
            <worktracker-page-header
                title=${this.t('my_page.title')}
                show-breadcrumbs
                breadcrumb-label=${this.t('my_page.title')}
            >
                <worktracker-icon-action
                    slot="actions"
                    icon="plus"
                    .title=${this.t('my_page.create_task')}
                    @action=${() => this._openCreateTask()}
                ></worktracker-icon-action>
            </worktracker-page-header>
            ${items.length > 0 ? html`
                <worktracker-list-section title=${this.t('my_page.title')} .count=${items.length}>
                    ${items.map((item) => html`
                        <div class="wt-list-row">
                            <worktracker-work-item-card
                                .item=${item}
                                variant="row"
                                ?show-preview=${false}
                                @changed=${() => this._reloadList()}
                            ></worktracker-work-item-card>
                        </div>
                    `)}
                </worktracker-list-section>
            ` : html`
                <div class="wt-empty">
                    <platform-icon class="wt-empty-icon" name="list-check" size="48"></platform-icon>
                    <p class="wt-empty-title">${this.t('my_page.empty')}</p>
                </div>
            `}
        `;
    }
}

customElements.define('worktracker-my-tasks-page', WorktrackerMyTasksPage);
