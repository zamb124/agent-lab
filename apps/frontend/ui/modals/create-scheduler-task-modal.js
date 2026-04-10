/**
 * Модальное окно для создания задачи планировщика
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class CreateSchedulerTaskModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .schedule-fields {
                margin-top: var(--space-4, 16px);
            }

            .actions-row {
                display: flex;
                gap: 12px;
            }

            .actions-row .btn {
                flex: 1;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.open = true;
        this._loading = false;
        this._targetService = 'flows';
        this._taskName = '';
        this._scheduleType = 'interval';
        this._cron = '*/5 * * * *';
        this._intervalSeconds = 60;
        this._runAt = '';
        this._payload = '{}';
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    close() {
        this.open = false;
        super.close();
        this.dispatchEvent(new CustomEvent('close'));
    }

    _handleClose() {
        this.close();
    }

    renderHeader() {
        return this.i18n.t('scheduler_modal.header', {});
    }

    renderBody() {
        const td = (k, p) => this.i18n.t(k, p ?? {});

        return html`
            <div class="form-group">
                <label class="form-label">${td('scheduler_modal.label_service')}</label>
                <input
                    class="form-input"
                    type="text"
                    placeholder="flows"
                    .value=${this._targetService}
                    @input=${(e) => { this._targetService = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                />
            </div>

            <div class="form-group">
                <label class="form-label">${td('scheduler_modal.label_task')}</label>
                <input
                    class="form-input"
                    type="text"
                    placeholder="sync_llm_models_task"
                    .value=${this._taskName}
                    @input=${(e) => { this._taskName = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                />
            </div>

            <div class="form-group">
                <label class="form-label">${td('scheduler_modal.label_type')}</label>
                <select
                    class="form-select"
                    .value=${this._scheduleType}
                    @change=${(e) => { this._scheduleType = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                >
                    <option value="interval">interval</option>
                    <option value="cron">cron</option>
                    <option value="one_time">one_time</option>
                </select>
            </div>

            <div class="schedule-fields">
                ${this._renderScheduleFields()}
            </div>

            <div class="form-group">
                <label class="form-label">${td('scheduler_modal.label_payload')}</label>
                <textarea
                    class="form-input"
                    rows="3"
                    placeholder="{}"
                    .value=${this._payload}
                    @input=${(e) => { this._payload = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                ></textarea>
            </div>
        `;
    }

    _renderScheduleFields() {
        const td = (k, p) => this.i18n.t(k, p ?? {});

        if (this._scheduleType === 'cron') {
            return html`
                <div class="form-group">
                    <label class="form-label">${td('scheduler_modal.label_cron')}</label>
                    <input
                        class="form-input"
                        type="text"
                        placeholder="*/5 * * * *"
                        .value=${this._cron}
                        @input=${(e) => { this._cron = e.target.value; this.requestUpdate(); }}
                        ?disabled=${this._loading}
                    />
                </div>
            `;
        }

        if (this._scheduleType === 'interval') {
            return html`
                <div class="form-group">
                    <label class="form-label">${td('scheduler_modal.label_interval')}</label>
                    <input
                        class="form-input"
                        type="number"
                        min="1"
                        placeholder="60"
                        .value=${String(this._intervalSeconds)}
                        @input=${(e) => { this._intervalSeconds = Number(e.target.value); this.requestUpdate(); }}
                        ?disabled=${this._loading}
                    />
                </div>
            `;
        }

        if (this._scheduleType === 'one_time') {
            return html`
                <div class="form-group">
                    <label class="form-label">${td('scheduler_modal.label_run_at')}</label>
                    <input
                        class="form-input"
                        type="datetime-local"
                        .value=${this._runAt}
                        @input=${(e) => { this._runAt = e.target.value; this.requestUpdate(); }}
                        ?disabled=${this._loading}
                    />
                </div>
            `;
        }

        return html``;
    }

    renderSaveHeaderButton() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        const title = this._loading ? td('scheduler_modal.creating') : td('scheduler_modal.submit');
        return this._renderHeaderSaveIcon({
            onClick: () => this._handleSubmit(),
            disabled: this._loading,
            title,
        });
    }

    renderFooter() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        return html`
            <div class="actions-row">
                <button
                    class="btn btn-secondary"
                    @click=${this._handleClose}
                    ?disabled=${this._loading}
                >
                    ${td('scheduler_modal.cancel')}
                </button>
            </div>
        `;
    }

    async _handleSubmit() {
        const td = (k, p) => this.i18n.t(k, p ?? {});

        if (!this._targetService.trim()) {
            this.error(td('scheduler_modal.err_service'));
            return;
        }
        if (!this._taskName.trim()) {
            this.error(td('scheduler_modal.err_task'));
            return;
        }

        const payload = JSON.parse(this._payload);
        const request = {
            target_service: this._targetService.trim(),
            task_name: this._taskName.trim(),
            schedule_type: this._scheduleType,
            timezone: 'UTC',
            payload,
        };

        if (this._scheduleType === 'cron') {
            request.cron = this._cron;
        } else if (this._scheduleType === 'interval') {
            request.interval_seconds = this._intervalSeconds;
        } else if (this._scheduleType === 'one_time') {
            if (!this._runAt) {
                this.error(td('scheduler_modal.err_run_at'));
                return;
            }
            request.run_at = new Date(this._runAt).toISOString();
        }

        this._loading = true;
        this.requestUpdate();

        await this.services.get('schedulerTasks').create(request);
        this.success(td('scheduler_modal.toast_created'));
        this.dispatchEvent(new CustomEvent('created'));
        this._handleClose();

        this._loading = false;
        this.requestUpdate();
    }
}

customElements.define('create-scheduler-task-modal', CreateSchedulerTaskModal);
