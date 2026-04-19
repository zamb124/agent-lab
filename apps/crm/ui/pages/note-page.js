/**
 * CRMNotePage — детальная страница заметки CRM.
 *
 * Маршрут: `/crm/notes/:itemId`. Поддерживает три случая, всё через один
 * компонент `<crm-note-card-view>`:
 *   - `itemId === 'new'` или `'draft-*'` — создание заметки (mode=`edit`,
 *     note=null).
 *   - `itemId === <real id>` — view-режим (mode=`view`, note=entity), edit
 *     включается по emit `edit-note`.
 *
 * Источники данных:
 *   - `useResource('crm/entities')`           — entity заметки по id.
 *   - `useOp('crm/entity_card')`              — карточка с related/relationships.
 *   - `useResource('crm/relationship_types')` — подписи типов связей.
 *
 * Обработка событий от note-card-view:
 *   - `edit-note`               → mode=`edit`.
 *   - `cancel`                  → mode=`view` (или navigate('notes') для draft).
 *   - `saved` { entity }        → mode=`view` + перезагрузка card.
 *   - `created` { entity }      → navigate на новый id.
 *   - `show-graph`              → openModal('crm.note_graph').
 *   - `delete-note`             → openModal('crm.entity_delete', redirectRoute='notes').
 *   - `entity-open` { entityId} → toast (страница entity-detail в G/4).
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '../components/note-card-view.js';

export class CRMNotePage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        noteId: { type: String },
        _card: { state: true },
        _cardError: { state: true },
        _mode: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .body {
                flex: 1;
                min-height: 0;
                padding: 0 var(--space-4) var(--space-4);
                overflow: hidden;
            }

            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                height: 100%;
                color: var(--text-secondary);
                text-align: center;
                padding: var(--space-6);
            }
            .center .icon { color: var(--text-tertiary); }
            .center h2 {
                margin: 0;
                font-size: var(--text-lg);
                color: var(--text-primary);
            }
            .center p {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                max-width: 480px;
            }

            .back-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke, var(--glass-border-medium));
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background var(--duration-fast);
            }
            .back-btn:hover { background: var(--glass-tint-medium); }
        `,
    ];

    constructor() {
        super();
        this.noteId = '';
        this._card = null;
        this._cardError = '';
        this._mode = 'view';
        this._lastRequestedId = '';
        this._entities = this.useResource('crm/entities');
        this._cardOp = this.useOp('crm/entity_card');
        this._relTypes = this.useResource('crm/relationship_types', { autoload: true });

        this._namespaceSelectionSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return 'all';
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const selection = map[cid];
            if (selection === 'all' || selection === undefined) return 'all';
            return selection;
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent('crm/note/updated', (event) => {
            const noteId = event && event.payload ? event.payload.note_id : null;
            if (typeof noteId !== 'string' || noteId !== this.noteId) {
                return;
            }
            this._reloadCurrent();
        });
        this.useEvent(this._cardOp.op.events.SUCCEEDED, (event) => {
            const result = event.payload && event.payload.result ? event.payload.result : null;
            if (!result || typeof result !== 'object') {
                throw new Error('crm/entity_card SUCCEEDED: payload.result missing');
            }
            this._card = result;
            this._cardError = '';
        });
        this.useEvent(this._cardOp.op.events.FAILED, (event) => {
            const err = event.payload && event.payload.error ? event.payload.error : null;
            this._card = null;
            this._cardError = err && typeof err.message === 'string' ? err.message : 'load_failed';
        });
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this.requestUpdate());
    }

    willUpdate(changed) {
        if (!changed.has('noteId')) {
            return;
        }
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            this._card = null;
            this._cardError = '';
            this._lastRequestedId = '';
            this._mode = 'view';
            return;
        }
        if (this._isDraftId(this.noteId)) {
            this._card = null;
            this._cardError = '';
            this._mode = 'edit';
            return;
        }
        if (this._lastRequestedId === this.noteId) {
            return;
        }
        this._lastRequestedId = this.noteId;
        this._mode = 'view';
        this._reloadCurrent();
    }

    _isDraftId(value) {
        return value === 'new' || (typeof value === 'string' && value.startsWith('draft-'));
    }

    _reloadCurrent() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0 || this._isDraftId(this.noteId)) {
            return;
        }
        this._entities.get(this.noteId);
        this._cardOp.run({ entity_id: this.noteId });
    }

    _resolveNote() {
        const byId = this._entities.byId;
        if (byId && byId[this.noteId]) {
            return byId[this.noteId];
        }
        return null;
    }

    _currentNamespace() {
        const selection = this._namespaceSelectionSel.value;
        if (selection === 'all' || selection === null || selection === undefined) {
            return 'default';
        }
        return selection;
    }

    _onBackToNotes() {
        this.navigate('notes');
    }

    _onEntityOpen(event) {
        const entityId = event.detail && event.detail.entityId ? event.detail.entityId : '';
        if (typeof entityId !== 'string' || entityId.length === 0) {
            return;
        }
        this.navigate('entity', { itemId: entityId });
    }

    _onShowGraph() {
        this.openModal('crm.note_graph', { noteId: this.noteId });
    }

    _onDeleteNote() {
        this.openModal('crm.entity_delete', { entityId: this.noteId, redirectRoute: 'notes' });
    }

    _onEditNote() {
        this._mode = 'edit';
    }

    _onEditCancel() {
        if (this._isDraftId(this.noteId)) {
            this.navigate('notes');
            return;
        }
        this._mode = 'view';
    }

    _onEditSaved() {
        this._mode = 'view';
        this._reloadCurrent();
    }

    _onEditCreated(event) {
        const created = event.detail && event.detail.entity ? event.detail.entity : null;
        if (!created || typeof created.entity_id !== 'string') return;
        this.navigate('note', { itemId: created.entity_id });
    }

    _noteLabel(note) {
        if (!note) return '';
        if (typeof note.title === 'string' && note.title.trim().length > 0) return note.title.trim();
        if (typeof note.entity_id === 'string') return note.entity_id;
        return '';
    }

    render() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            return html`
                <div class="body">
                    <div class="center">
                        <platform-icon class="icon" name="info" size="48"></platform-icon>
                        <h2>${this.t('note_page.no_id_title')}</h2>
                        <p>${this.t('note_page.no_id_message')}</p>
                        <button class="back-btn" type="button" @click=${this._onBackToNotes}>
                            <platform-icon name="arrow-left" size="16"></platform-icon>
                            ${this.t('note_page.back_to_notes')}
                        </button>
                    </div>
                </div>
            `;
        }

        if (this._isDraftId(this.noteId)) {
            return html`
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this.t('note_page.draft_breadcrumb')}></platform-breadcrumbs>
                </div>
                <div class="body edit">
                    <crm-note-card-view
                        .note=${null}
                        mode="edit"
                        defaultNamespace=${this._currentNamespace()}
                        @cancel=${this._onEditCancel}
                        @created=${this._onEditCreated}
                    ></crm-note-card-view>
                </div>
            `;
        }

        if (this._cardError) {
            return html`
                <div class="body">
                    <div class="center">
                        <platform-icon class="icon" name="warning" size="48"></platform-icon>
                        <h2>${this.t('note_page.not_found_title')}</h2>
                        <p>${this._cardError}</p>
                        <button class="back-btn" type="button" @click=${this._onBackToNotes}>
                            <platform-icon name="arrow-left" size="16"></platform-icon>
                            ${this.t('note_page.back_to_notes')}
                        </button>
                    </div>
                </div>
            `;
        }

        const note = this._resolveNote();
        const entityLoading = this._entities.loading;
        const cardLoading = this._cardOp.busy;

        if (!note || entityLoading) {
            return html`
                <div class="body">
                    <div class="center">
                        <glass-spinner size="lg"></glass-spinner>
                        <p>${this.t('note_page.loading')}</p>
                    </div>
                </div>
            `;
        }

        if (this._mode === 'edit') {
            return html`
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this._noteLabel(note)}></platform-breadcrumbs>
                </div>
                <div class="body edit">
                    <crm-note-card-view
                        .note=${note}
                        mode="edit"
                        @cancel=${this._onEditCancel}
                        @saved=${this._onEditSaved}
                    ></crm-note-card-view>
                </div>
            `;
        }

        if (cardLoading || !this._card) {
            return html`
                <div class="body">
                    <div class="center">
                        <glass-spinner size="lg"></glass-spinner>
                        <p>${this.t('note_page.loading')}</p>
                    </div>
                </div>
            `;
        }

        const relationshipTypes = Array.isArray(this._relTypes.items) ? this._relTypes.items : [];
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${this._noteLabel(note)}></platform-breadcrumbs>
            </div>
            <div class="body">
                <crm-note-card-view
                    .note=${note}
                    .card=${this._card}
                    .relationshipTypes=${relationshipTypes}
                    mode="view"
                    @entity-open=${this._onEntityOpen}
                    @show-graph=${this._onShowGraph}
                    @delete-note=${this._onDeleteNote}
                    @edit-note=${this._onEditNote}
                ></crm-note-card-view>
            </div>
            ${nothing}
        `;
    }
}

customElements.define('crm-note-page', CRMNotePage);
