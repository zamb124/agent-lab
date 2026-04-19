/**
 * Create scheduler task modal — конструктор PlatformScheduleCreateRequest.
 *
 * Поля API (core/scheduler/models.py):
 *   target_service: str (required)
 *   task_name:      str (required)
 *   queue_name:     str | null
 *   schedule_type:  cron | interval | one_time
 *   cron:           str (when type=cron)
 *   interval_seconds: int (when type=interval)
 *   run_at:         ISO datetime (when type=one_time)
 *   timezone:       str (default UTC)
 *   payload:        Dict[str, Any] (kwargs для taskiq task)
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

export class FrontendCreateSchedulerTaskModal extends PlatformFormModal {
    static modalKind = 'frontend.scheduler_task_create';

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .type-row { display: flex; gap: var(--space-2); }
            .type-btn {
                flex: 1;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                background: transparent;
                color: var(--text-secondary);
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: var(--text-sm);
            }
            .type-btn[data-active="true"] {
                border-color: var(--accent);
                background: var(--accent-soft, rgba(99,102,241,0.1));
                color: var(--text-primary);
            }
            .json-textarea {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                min-height: 120px;
            }
            .field-help {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: 4px;
            }
        `,
    ];

    static properties = {
        ...PlatformFormModal.properties,
        _targetService: { state: true },
        _taskName: { state: true },
        _queueName: { state: true },
        _scheduleType: { state: true },
        _cron: { state: true },
        _intervalSeconds: { state: true },
        _runAt: { state: true },
        _timezone: { state: true },
        _payloadJson: { state: true },
    };

    constructor() {
        super();
        this._targetService = '';
        this._taskName = '';
        this._queueName = '';
        this._scheduleType = 'cron';
        this._cron = '';
        this._intervalSeconds = '';
        this._runAt = '';
        this._timezone = 'UTC';
        this._payloadJson = '{}';
        this.size = 'lg';
        this._tasks = this.useResource('frontend/scheduler_tasks');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('scheduler_modal.header');
    }

    validateForm() {
        const errors = {};
        if (!this._targetService.trim()) errors.target_service = this.t('scheduler_modal.err_service');
        if (!this._taskName.trim()) errors.task_name = this.t('scheduler_modal.err_task');
        if (this._scheduleType === 'cron' && !this._cron.trim()) {
            errors.cron = this.t('scheduler_modal.err_task');
        }
        if (this._scheduleType === 'interval') {
            const sec = Number(this._intervalSeconds);
            if (!sec || sec < 1) errors.interval_seconds = this.t('scheduler_modal.err_task');
        }
        if (this._scheduleType === 'one_time' && !this._runAt) {
            errors.run_at = this.t('scheduler_modal.err_run_at');
        }
        const trimmed = (this._payloadJson || '').trim();
        if (trimmed) {
            try { JSON.parse(trimmed); }
            catch { errors.payload = this.t('scheduler_modal.err_payload_invalid'); }
        }
        return errors;
    }

    async handleSubmit() {
        const trimmed = (this._payloadJson || '').trim();
        const payload = trimmed ? JSON.parse(trimmed) : {};
        const body = {
            target_service: this._targetService.trim(),
            task_name: this._taskName.trim(),
            schedule_type: this._scheduleType,
            timezone: this._timezone.trim() || 'UTC',
            payload,
        };
        if (this._queueName.trim()) body.queue_name = this._queueName.trim();
        if (this._scheduleType === 'cron') body.cron = this._cron.trim();
        if (this._scheduleType === 'interval') body.interval_seconds = Number(this._intervalSeconds);
        if (this._scheduleType === 'one_time') body.run_at = new Date(this._runAt).toISOString();
        this._tasks.create(body);
        this.closeAfterSave();
    }

    _setType(type) {
        this._scheduleType = type;
        this.isDirty = true;
    }

    _renderTypeSelector() {
        const types = [
            { id: 'cron', label: this.t('scheduler_modal.type_cron') },
            { id: 'interval', label: this.t('scheduler_modal.type_interval') },
            { id: 'one_time', label: this.t('scheduler_modal.type_one_time') },
        ];
        return html`
            <div class="form-group">
                <label class="form-label">${this.t('scheduler_modal.label_type')}</label>
                <div class="type-row">
                    ${types.map((t) => html`
                        <button type="button" class="type-btn"
                            data-active=${this._scheduleType === t.id ? 'true' : 'false'}
                            @click=${() => this._setType(t.id)}
                        >${t.label}</button>
                    `)}
                </div>
            </div>
        `;
    }

    _renderTypeFields() {
        if (this._scheduleType === 'cron') {
            return html`
                <div class="form-group">
                    <label class="form-label">${this.t('scheduler_modal.label_cron')}</label>
                    <input class="form-input" name="cron" .value=${this._cron}
                        @input=${(e) => { this._cron = e.target.value; }}
                        placeholder="0 */5 * * *"
                    />
                    ${this.renderFieldError('cron')}
                </div>
            `;
        }
        if (this._scheduleType === 'interval') {
            return html`
                <div class="form-group">
                    <label class="form-label">${this.t('scheduler_modal.label_interval')}</label>
                    <input class="form-input" name="interval_seconds" type="number" min="1"
                        .value=${this._intervalSeconds}
                        @input=${(e) => { this._intervalSeconds = e.target.value; }}
                        placeholder="60"
                    />
                    ${this.renderFieldError('interval_seconds')}
                </div>
            `;
        }
        return html`
            <div class="form-group">
                <label class="form-label">${this.t('scheduler_modal.label_run_at')}</label>
                <input class="form-input" name="run_at" type="datetime-local"
                    .value=${this._runAt}
                    @input=${(e) => { this._runAt = e.target.value; }}
                />
                ${this.renderFieldError('run_at')}
            </div>
        `;
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="form-group">
                    <label class="form-label">${this.t('scheduler_modal.label_service')}</label>
                    <input class="form-input" name="target_service" .value=${this._targetService}
                        @input=${(e) => { this._targetService = e.target.value; }}
                        placeholder=${this.t('scheduler_page.prompt_target')}
                        autofocus
                    />
                    ${this.renderFieldError('target_service')}
                </div>

                <div class="form-group">
                    <label class="form-label">${this.t('scheduler_modal.label_task')}</label>
                    <input class="form-input" name="task_name" .value=${this._taskName}
                        @input=${(e) => { this._taskName = e.target.value; }}
                        placeholder=${this.t('scheduler_page.prompt_task')}
                    />
                    ${this.renderFieldError('task_name')}
                </div>

                <div class="form-group">
                    <label class="form-label">queue_name</label>
                    <input class="form-input" name="queue_name" .value=${this._queueName}
                        @input=${(e) => { this._queueName = e.target.value; }}
                    />
                </div>

                ${this._renderTypeSelector()}
                ${this._renderTypeFields()}

                <div class="form-group">
                    <label class="form-label">timezone</label>
                    <input class="form-input" name="timezone" .value=${this._timezone}
                        @input=${(e) => { this._timezone = e.target.value; }}
                        placeholder="UTC"
                    />
                </div>

                <div class="form-group">
                    <label class="form-label">${this.t('scheduler_modal.label_payload')}</label>
                    <textarea class="form-input json-textarea" name="payload"
                        .value=${this._payloadJson}
                        @input=${(e) => { this._payloadJson = e.target.value; }}
                    ></textarea>
                    ${this.renderFieldError('payload')}
                    <div class="field-help">${this.t('scheduler_page.prompt_payload')}</div>
                </div>
            </form>
        `;
    }

    renderFooter() {
        const canSubmit = this._targetService.trim() && this._taskName.trim() && !this.loading;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('scheduler_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${this.loading
                        ? this.t('scheduler_modal.creating')
                        : this.t('scheduler_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-create-scheduler-task-modal', FrontendCreateSchedulerTaskModal);
registerModalKind(FrontendCreateSchedulerTaskModal.modalKind, 'frontend-create-scheduler-task-modal');
