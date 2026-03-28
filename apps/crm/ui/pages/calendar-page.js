import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveObjectName } from '@platform/lib/utils/entity-ref.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

function toIsoDate(value) {
    if (!value) {
        return null;
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return null;
    }
    return date.toISOString().slice(0, 10);
}

function formatDateLabel(dateIso) {
    const date = new Date(dateIso);
    return date.toLocaleDateString('ru-RU', {
        weekday: 'short',
        day: 'numeric',
        month: 'long',
    });
}

export class CalendarPage extends PlatformElement {
    static properties = {
        _events: { state: true },
        _period: { state: true },
        _selectedDate: { state: true },
        _summary: { state: true },
        _loading: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-2xl);
                overflow: hidden;
            }

            .toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
                background: var(--crm-surface-tint);
                flex-wrap: wrap;
            }

            .title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .toolbar-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .period-select,
            .date-input {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .layout {
                flex: 1;
                min-height: 0;
                display: grid;
                grid-template-columns: 320px 1fr;
                gap: var(--space-3);
                padding: var(--space-4);
                overflow: auto;
            }

            .summary,
            .events {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface-muted);
                overflow: hidden;
                display: flex;
                flex-direction: column;
                min-height: 0;
            }

            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .panel-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .panel-body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .summary-text {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.45;
                white-space: pre-wrap;
            }

            .event-day {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                overflow: hidden;
            }

            .event-day-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .event-day-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }

            .event-day-count {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--crm-surface-tint-strong);
                border-radius: var(--radius-full);
                padding: var(--space-1) var(--space-2);
            }

            .event-list {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-2);
            }

            .event-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                color: var(--text-primary);
                text-align: left;
            }

            .event-item:hover {
                border-color: var(--crm-selected-stroke);
            }

            .event-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .event-name {
                flex: 1;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }

            .empty {
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                gap: var(--space-2);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-8);
            }

            @media (max-width: 1023px) {
                .layout {
                    grid-template-columns: 1fr;
                }
            }

            @media (max-width: 767px) {
                :host {
                    border: none;
                    border-radius: 0;
                }

                .toolbar {
                    padding: var(--space-3);
                }

                .layout {
                    padding: var(--space-3);
                }
            }
        `,
    ];

    constructor() {
        super();
        this._events = [];
        this._period = 'week';
        this._selectedDate = new Date().toISOString().slice(0, 10);
        this._summary = '';
        this._loading = false;
        this._onPlatformNotification = this._onPlatformNotification.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('platform-notification-received', this._onPlatformNotification);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('platform-notification-received', this._onPlatformNotification);
    }

    async firstUpdated() {
        await this._loadCalendarData();
    }

    _normalizeNamespaceName(namespace) {
        const normalized = resolveObjectName(namespace, null);
        if (!normalized) {
            return 'all';
        }
        return normalized;
    }

    _onPlatformNotification(event) {
        const notification = event.detail;
        if (!notification || notification.service !== 'crm') {
            return;
        }
        if (notification.type !== 'crm_daily_summary_updated') {
            return;
        }
        const payload = notification.data;
        if (!payload || payload.event !== 'crm.daily_summary.updated') {
            return;
        }
        const selectedNamespace = this._normalizeNamespaceName(CRMStore.state.namespaces.current);
        const payloadNamespace = this._normalizeNamespaceName(payload.namespace);
        if (selectedNamespace !== payloadNamespace) {
            return;
        }
        if (payload.date !== this._selectedDate) {
            return;
        }
        const summaryState = payload.summary_state;
        if (!summaryState || typeof summaryState !== 'object') {
            throw new Error('summary_state must be object');
        }
        const summary = summaryState.summary;
        this._summary = typeof summary === 'string' ? summary : '';
        this._loading = false;
    }

    async _loadCalendarData() {
        this._loading = true;
        const crmApi = this.crmApi;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        const [notes, tasks, summary] = await Promise.all([
            crmApi.getEntities({ entity_type: 'note', namespace: namespaceName, limit: 200 }),
            crmApi.getEntities({ entity_type: 'task', namespace: namespaceName, limit: 200 }),
            crmApi.getDailySummary(this._selectedDate, { namespace: namespaceName }),
        ]);

        const mergedEvents = [...(Array.isArray(notes) ? notes : []), ...(Array.isArray(tasks) ? tasks : [])]
            .map((entity) => {
                const dateValue = toIsoDate(entity.note_date || entity.due_date || entity.created_at);
                if (!dateValue) {
                    return null;
                }
                return {
                    date: dateValue,
                    entityId: entity.entity_id,
                    name: entity.name || 'Без названия',
                    type: entity.entity_type || 'entity',
                };
            })
            .filter(Boolean);

        this._events = mergedEvents.sort((left, right) => left.date.localeCompare(right.date));
        this._summary = typeof summary === 'string' ? summary : (summary?.summary || '');
        this._loading = false;
    }

    _openEntity(entityId) {
        CRMStore.setCurrentView('entities');
        CRMStore.setCurrentEntity(entityId);
    }

    _periodDays() {
        return this._period === 'week' ? 7 : 31;
    }

    _eventDays() {
        const startDate = new Date(this._selectedDate);
        const endDate = new Date(startDate);
        endDate.setDate(startDate.getDate() + this._periodDays() - 1);

        const byDate = new Map();
        for (const event of this._events) {
            if (!byDate.has(event.date)) {
                byDate.set(event.date, []);
            }
            byDate.get(event.date).push(event);
        }

        const rows = [];
        const cursor = new Date(startDate);
        while (cursor <= endDate) {
            const isoDate = cursor.toISOString().slice(0, 10);
            rows.push({
                date: isoDate,
                label: formatDateLabel(isoDate),
                events: byDate.get(isoDate) || [],
            });
            cursor.setDate(cursor.getDate() + 1);
        }
        return rows;
    }

    render() {
        const days = this._eventDays();
        const totalEvents = days.reduce((acc, day) => acc + day.events.length, 0);
        return html`
            <div class="toolbar">
                <div class="title">
                    <platform-icon name="calendar" size="18"></platform-icon>
                    <span>Календарь</span>
                </div>
                <div class="toolbar-actions">
                    <select class="period-select" .value=${this._period} @change=${(event) => { this._period = event.target.value; }}>
                        <option value="week">Неделя</option>
                        <option value="month">Месяц</option>
                    </select>
                    <platform-date-picker
                        class="date-input"
                        mode="date"
                        value-format="iso"
                        .value=${this._selectedDate}
                        @change=${(event) => { this._selectedDate = event.target.value; this._loadCalendarData(); }}
                    ></platform-date-picker>
                    <button class="btn btn-secondary" type="button" @click=${this._loadCalendarData}>
                        Обновить
                    </button>
                </div>
            </div>

            <div class="layout">
                <section class="summary">
                    <div class="panel-header">
                        <div class="panel-title">AI summary</div>
                    </div>
                    <div class="panel-body">
                        ${this._loading ? html`
                            <div class="empty">Генерируем summary...</div>
                        ` : this._summary ? html`
                            <div class="summary-text">${this._summary}</div>
                        ` : html`
                            <div class="empty">Summary пока недоступен</div>
                        `}
                    </div>
                </section>

                <section class="events">
                    <div class="panel-header">
                        <div class="panel-title">События периода</div>
                        <div class="event-day-count">${totalEvents}</div>
                    </div>
                    <div class="panel-body">
                        ${this._loading ? html`
                            <div class="empty">Загрузка событий...</div>
                        ` : days.map((day) => html`
                            <article class="event-day">
                                <div class="event-day-header">
                                    <div class="event-day-title">${day.label}</div>
                                    <div class="event-day-count">${day.events.length}</div>
                                </div>
                                <div class="event-list">
                                    ${day.events.length === 0 ? html`
                                        <div class="event-type">Нет событий</div>
                                    ` : day.events.map((event) => html`
                                        <button class="event-item" type="button" @click=${() => this._openEntity(event.entityId)}>
                                            <span class="event-type">${event.type}</span>
                                            <span class="event-name">${event.name}</span>
                                        </button>
                                    `)}
                                </div>
                            </article>
                        `)}
                    </div>
                </section>
            </div>
        `;
    }
}

customElements.define('calendar-page', CalendarPage);
