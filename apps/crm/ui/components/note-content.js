import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class NoteContent extends PlatformElement {
    static properties = {
        note: { type: Object },
        relatedEntities: { type: Array },
        summaryText: { type: String },
        summaryGeneratedAt: { type: String },
        summaryEntities: { type: Array },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
            }

            .layout {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 440px;
                gap: 24px;
                align-items: start;
            }

            .note-main {
                display: flex;
                flex-direction: column;
                gap: 24px;
                min-height: 0;
            }

            .note-header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 24px;
            }

            .note-title-wrap {
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .note-title {
                margin: 0;
                font-size: 28px;
                line-height: 34px;
                font-weight: 700;
                color: var(--text-primary);
            }

            .note-date {
                margin: 0;
                font-size: 16px;
                line-height: 20px;
                color: rgba(34, 34, 34, 0.3);
            }

            .note-actions {
                display: inline-flex;
                align-items: center;
                gap: 16px;
            }

            .round-btn {
                width: 44px;
                height: 44px;
                border: none;
                border-radius: 22px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                background: rgba(34, 34, 34, 0.05);
                color: rgba(34, 34, 34, 0.7);
            }

            .round-btn.danger {
                background: rgba(255, 136, 92, 0.15);
                color: #ff885c;
            }

            .edit-btn {
                height: 44px;
                border: none;
                border-radius: 22px;
                padding: 0 24px;
                background: #99a6f9;
                color: #ffffff;
                font-size: 16px;
                line-height: 20px;
                cursor: pointer;
            }

            .note-text {
                margin: 0;
                white-space: pre-wrap;
                font-size: 16px;
                line-height: 20px;
                color: var(--text-primary);
            }

            .sidebar {
                display: flex;
                flex-direction: column;
                gap: 24px;
                min-height: 0;
            }

            .card {
                border-radius: 16px;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 16px;
            }

            .summary-card {
                background: rgba(153, 166, 249, 0.2);
            }

            .tasks-card {
                background: rgba(34, 34, 34, 0.05);
            }

            .entities-section {
                display: flex;
                flex-direction: column;
                gap: 20px;
                padding-bottom: 24px;
            }

            .card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }

            .summary-title {
                margin: 0;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                background: linear-gradient(80.46deg, #fad17a 9.08%, #ff9a76 44.12%, #99a6f9 85.61%);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
            }

            .summary-meta {
                margin: 0;
                color: rgba(34, 34, 34, 0.3);
                font-size: 12px;
                line-height: 15px;
            }

            .summary-text {
                margin: 0;
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
            }

            .summary-tags {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
            }

            .summary-tag {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 12px;
                min-height: 24px;
                border-radius: 14px;
                font-size: 12px;
                line-height: 15px;
                background: #99a6f9;
                color: rgba(34, 34, 34, 0.95);
            }

            .tasks-title,
            .entities-title {
                margin: 0;
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                color: var(--text-primary);
            }

            .tasks-list {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            .task-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                min-height: 32px;
            }

            .task-main {
                display: inline-flex;
                align-items: center;
                gap: 12px;
                min-width: 0;
                flex: 1;
            }

            .checkbox {
                width: 24px;
                height: 24px;
                border-radius: 4px;
                flex-shrink: 0;
                border: 2px solid rgba(34, 34, 34, 0.05);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .checkbox.checked {
                background: #99a6f9;
                border-color: #99a6f9;
                color: #ffffff;
            }

            .task-text {
                min-width: 0;
                font-size: 16px;
                line-height: 20px;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .task-text.completed {
                color: rgba(34, 34, 34, 0.2);
                text-decoration: line-through;
            }

            .task-remove {
                width: 24px;
                height: 24px;
                border: none;
                border-radius: 12px;
                background: transparent;
                color: rgba(34, 34, 34, 0.2);
                flex-shrink: 0;
            }

            .entity-link {
                border: none;
                width: 100%;
                text-align: left;
                display: flex;
                align-items: flex-start;
                gap: 12px;
                padding: 12px;
                border-radius: 16px;
                cursor: pointer;
                background: rgba(153, 166, 249, 0.2);
            }

            .entity-link.tone-yellow {
                background: rgba(250, 209, 122, 0.3);
            }

            .entity-link.tone-orange {
                background: rgba(255, 136, 92, 0.2);
            }

            .entity-avatar {
                width: 64px;
                height: 64px;
                border-radius: 12px;
                overflow: hidden;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(312.35deg, #fad17a 18.71%, #ff9a76 82.25%, #99a6f9 157.48%);
            }

            .entity-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .entity-data {
                display: flex;
                flex-direction: column;
                gap: 12px;
                min-width: 0;
                flex: 1;
            }

            .entity-name {
                margin: 0;
                font-size: 16px;
                line-height: 20px;
                font-weight: 600;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .entity-subtitle {
                margin: 0;
                font-size: 12px;
                line-height: 12px;
                color: rgba(34, 34, 34, 0.2);
            }

            .entity-score {
                height: 16px;
                border-radius: 8px;
                background: rgba(34, 34, 34, 0.05);
                overflow: hidden;
                position: relative;
            }

            .entity-score-fill {
                height: 100%;
                width: var(--score, 80%);
                background: #99a6f9;
            }

            .entity-score-fill.tone-yellow {
                background: #fad17a;
            }

            .entity-score-fill.tone-orange {
                background: #ff885c;
            }

            @media (max-width: 1279px) {
                .layout {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.note = null;
        this.relatedEntities = [];
        this.summaryText = '';
        this.summaryGeneratedAt = '';
        this.summaryEntities = [];
    }

    _formatNoteDate(dateValue) {
        if (typeof dateValue !== 'string' || dateValue.trim().length === 0) {
            return '';
        }
        const date = new Date(dateValue);
        if (Number.isNaN(date.getTime())) {
            throw new Error('Invalid note date');
        }
        return date.toLocaleDateString('ru-RU', {
            day: 'numeric',
            month: 'long',
            year: 'numeric',
        });
    }

    _getTaskEntities() {
        if (!Array.isArray(this.relatedEntities)) {
            throw new Error('relatedEntities must be an array');
        }
        return this.relatedEntities.filter((entity) => entity?.entity_type === 'task');
    }

    _getNonTaskEntities() {
        if (!Array.isArray(this.relatedEntities)) {
            throw new Error('relatedEntities must be an array');
        }
        return this.relatedEntities.filter((entity) => entity?.entity_type !== 'task');
    }

    _getText(value, fallback) {
        if (typeof value === 'string' && value.trim().length > 0) {
            return value;
        }
        return fallback;
    }

    _getSummaryMeta() {
        if (typeof this.summaryGeneratedAt === 'string' && this.summaryGeneratedAt.trim().length > 0) {
            return `Сгенерирована в ${this.summaryGeneratedAt}`;
        }
        return 'Нет summary';
    }

    _getEntityAvatarUrl(entity) {
        const attrs = entity?.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        if (typeof attrs.avatar_url === 'string' && attrs.avatar_url.trim().length > 0) {
            return attrs.avatar_url;
        }
        return '';
    }

    _getEntitySubtitle(entity) {
        const subtype = this._getText(entity?.entity_subtype, '');
        if (subtype) {
            return subtype;
        }
        return this._getText(entity?.entity_type, 'entity');
    }

    _getEntityTone(index) {
        const tones = ['violet', 'yellow', 'orange'];
        return tones[index % tones.length];
    }

    _emitEntityOpen(entity) {
        if (!entity || typeof entity !== 'object') {
            throw new Error('Entity is required');
        }
        this.emit('entity-open', { entity });
    }

    render() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }

        const noteText = this._getText(this.note.description, 'Без описания');
        const noteTitle = this._getText(this.note.name, 'Заметка');
        const noteDate = this._formatNoteDate(this.note.note_date || this.note.updated_at || this.note.created_at);
        const taskEntities = this._getTaskEntities();
        const nonTaskEntities = this._getNonTaskEntities();
        const summaryTags = Array.isArray(this.summaryEntities) ? this.summaryEntities : [];

        return html`
            <div class="layout">
                <section class="note-main">
                    <div class="note-header">
                        <div class="note-title-wrap">
                            <h2 class="note-title">${noteTitle}</h2>
                            <p class="note-date">${noteDate}</p>
                        </div>
                        <div class="note-actions">
                            <button class="round-btn" type="button" title="Поделиться">
                                <platform-icon name="share" size="20"></platform-icon>
                            </button>
                            <button class="round-btn danger" type="button" title="Удалить">
                                <platform-icon name="delete" size="20"></platform-icon>
                            </button>
                            <button class="edit-btn" type="button">Редактировать</button>
                        </div>
                    </div>
                    <p class="note-text">${noteText}</p>
                </section>

                <aside class="sidebar">
                    <section class="card summary-card">
                        <div class="card-header">
                            <h3 class="summary-title">
                                <platform-icon name="ai" size="24" colored></platform-icon>
                                Daily summary
                            </h3>
                            <button class="round-btn" type="button" title="Обновить">
                                <platform-icon name="refresh" size="18" colored></platform-icon>
                            </button>
                        </div>
                        <p class="summary-meta">${this._getSummaryMeta()}</p>
                        <p class="summary-text">${this._getText(this.summaryText, 'Нет summary')}</p>
                        <div class="summary-tags">
                            ${summaryTags.map((tag) => html`
                                <span class="summary-tag">
                                    <platform-icon name="file" size="12"></platform-icon>
                                    ${tag}
                                </span>
                            `)}
                        </div>
                    </section>

                    <section class="card tasks-card">
                        <h3 class="tasks-title">Связанные задачи</h3>
                        <div class="tasks-list">
                            ${taskEntities.map((task) => {
                                const taskCompleted = task?.status === 'done' || task?.status === 'completed';
                                return html`
                                    <div class="task-row">
                                        <div class="task-main">
                                            <span class="checkbox ${taskCompleted ? 'checked' : ''}">
                                                ${taskCompleted ? html`<platform-icon name="check" size="14"></platform-icon>` : ''}
                                            </span>
                                            <span class="task-text ${taskCompleted ? 'completed' : ''}">${this._getText(task.name, 'Задача')}</span>
                                        </div>
                                        <button class="task-remove" type="button" aria-label="Удалить">
                                            <platform-icon name="close" size="14"></platform-icon>
                                        </button>
                                    </div>
                                `;
                            })}
                        </div>
                    </section>

                    <section class="entities-section">
                        <h3 class="entities-title">Связанные сущности</h3>
                        ${nonTaskEntities.map((entity, index) => {
                            const tone = this._getEntityTone(index);
                            const avatarUrl = this._getEntityAvatarUrl(entity);
                            return html`
                                <button
                                    class="entity-link ${tone === 'yellow' ? 'tone-yellow' : ''} ${tone === 'orange' ? 'tone-orange' : ''}"
                                    type="button"
                                    @click=${() => this._emitEntityOpen(entity)}
                                >
                                    <span class="entity-avatar">
                                        ${avatarUrl
                                            ? html`<img src=${avatarUrl} alt=${this._getText(entity.name, 'Entity')} />`
                                            : html`<platform-icon name="user" size="28"></platform-icon>`}
                                    </span>
                                    <span class="entity-data">
                                        <span>
                                            <p class="entity-name">${this._getText(entity.name, 'Entity')}</p>
                                            <p class="entity-subtitle">${this._getEntitySubtitle(entity)}</p>
                                        </span>
                                        <span class="entity-score">
                                            <span class="entity-score-fill ${tone === 'yellow' ? 'tone-yellow' : ''} ${tone === 'orange' ? 'tone-orange' : ''}"></span>
                                        </span>
                                    </span>
                                </button>
                            `;
                        })}
                    </section>
                </aside>
            </div>
        `;
    }
}

customElements.define('note-content', NoteContent);
