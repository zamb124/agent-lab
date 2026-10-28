/**
 * Боковая панель страницы: оглавление, обратные ссылки, комментарии, история.
 *
 * Панель — один компонент для двух мест: правая колонка на широком экране и
 * bottom-sheet на узком. Поэтому данные вкладок она грузит сама, а от хозяина
 * получает только страницу и оглавление (оглавление умеет считать лишь
 * открытый редактор).
 *
 * Ревизии подтягиваются лениво: вкладка истории открывается редко, а список
 * версий у активной страницы растёт с каждым сохранением.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { PropertyValues } from '@platform/lib/lit-shim.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController } from '@platform/lib/base/use-resource.js';

interface WikiOutlineItem {
    level: number;
    text: string;
    pos: number;
    [key: string]: unknown;
}

interface WikiBacklinkItem {
    wiki_page_id?: unknown;
    title?: unknown;
    [key: string]: unknown;
}

interface WikiCommentItem {
    wiki_comment_id?: string;
    author_user_id?: string;
    body_markdown?: unknown;
    resolved_at?: unknown;
    created_at?: string | number | Date;
    [key: string]: unknown;
}

interface WikiRevisionItem {
    wiki_revision_id?: string;
    author_user_id?: string;
    created_at?: string | number | Date;
    [key: string]: unknown;
}
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-user-chip.js';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function itemRecords(value: unknown, label: string): Record<string, unknown>[] {
    if (!isPlainRecord(value) || !Array.isArray(value.items)) {
        throw new Error(`${label}: lastResult.items required`);
    }
    const items: Record<string, unknown>[] = [];
    for (const item of value.items) {
        if (!isPlainRecord(item)) {
            throw new Error(`${label}: item must be an object`);
        }
        items.push(item);
    }
    return items;
}


export const WIKI_PANEL_TABS = Object.freeze(['outline', 'backlinks', 'comments', 'history']);

export class WikiPagePanel extends PlatformElement {
    static i18nNamespace = 'wiki';

    declare pageId: string;
    declare tab: string;
    declare outline: WikiOutlineItem[];
    declare embedded: boolean;
    declare _commentDraft: string;
    declare _selectedRevisionId: string;
    private _backlinks: OpController;
    private _commentsOp: OpController;
    private _commentCreate: OpController;
    private _commentResolve: OpController;
    private _revisions: OpController;
    private _revisionRead: OpController;
    private _revisionRestore: OpController;
    private _locale: SelectController<unknown>;

    static override properties = {
        pageId: { type: String, attribute: 'page-id' },
        tab: { type: String, reflect: true },
        /** `{ level, text, pos }[]` из `platform-rich-editor.getOutline()`. */
        outline: { attribute: false },
        /** В bottom-sheet рамка и крестик уже есть у листа. */
        embedded: { type: Boolean, reflect: true },
        _commentDraft: { state: true },
        _selectedRevisionId: { state: true },
    };

    static override styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-width: 0;
                height: 100%;
                overflow: hidden;
            }

            .head {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-3) var(--space-2);
            }

            /* В листе высоту задаёт лист, а не колонка страницы. */
            :host([embedded]) {
                height: auto;
            }

            :host([embedded]) .head {
                padding: 0 0 var(--space-2);
            }

            .body {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                padding: var(--space-2) var(--space-3) var(--space-6);
            }

            :host([embedded]) .body {
                padding: 0 0 var(--space-4);
            }

            .close-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
            }

            .close-btn:hover {
                background: var(--wiki-surface-muted);
                color: var(--text-primary);
            }

            .outline-item {
                display: block;
                width: 100%;
                padding: 3px 0;
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-family: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .outline-item:hover {
                color: var(--wiki-accent);
            }

            .backlink {
                display: block;
                padding: 4px 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-decoration: none;
                cursor: pointer;
            }

            .backlink:hover {
                color: var(--wiki-accent);
            }

            .comment {
                padding: var(--space-2) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .comment-body {
                margin-top: 4px;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                overflow-wrap: anywhere;
            }

            .comment-resolved {
                color: var(--success);
                font-size: var(--text-xs);
            }

            .comment-form {
                margin-top: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .comment-input {
                min-height: 64px;
                padding: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--wiki-surface-muted);
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm);
                resize: vertical;
            }

            .ghost-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 3px var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                font-family: inherit;
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .ghost-btn:hover {
                background: var(--wiki-surface-muted);
                color: var(--text-primary);
            }

            .revision {
                display: block;
                width: 100%;
                padding: var(--space-2);
                border: 1px solid transparent;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-secondary);
                font-family: inherit;
                text-align: left;
                cursor: pointer;
            }

            .revision:hover {
                background: var(--wiki-surface-muted);
            }

            .revision.is-selected {
                border-color: var(--wiki-accent);
                background: var(--wiki-accent-soft);
                color: var(--text-primary);
            }

            .revision-meta {
                margin-top: 2px;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .revision-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin: var(--space-2) 0;
            }

            .revision-preview {
                max-height: 18rem;
                overflow: auto;
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--wiki-surface-muted);
                color: var(--text-secondary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.6;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
            }

            .muted {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.pageId = '';
        this.tab = 'outline';
        this.outline = [];
        this.embedded = false;
        this._commentDraft = '';
        this._selectedRevisionId = '';
        this._backlinks = this.useOp('wiki/backlinks');
        this._commentsOp = this.useOp('wiki/comments');
        this._commentCreate = this.useOp('wiki/comment_create');
        this._commentResolve = this.useOp('wiki/comment_resolve');
        this._revisions = this.useOp('wiki/revisions');
        this._revisionRead = this.useOp('wiki/revision_read');
        this._revisionRestore = this.useOp('wiki/revision_restore');
        this._locale = this.select((state) => state.i18n.locale);
    }

    override connectedCallback() {
        super.connectedCallback();
        this._loadTab();
    }

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        if (changed.has('pageId')) {
            this._selectedRevisionId = '';
        }
        if (changed.has('pageId') || changed.has('tab')) {
            this._loadTab();
        }
    }

    /** Каждая вкладка тянет только своё: панель открывается точечно. */
    private _loadTab() {
        if (this.pageId === '') {
            return;
        }
        if (this.tab === 'backlinks') {
            void this._backlinks.run({ target_kind: 'wiki_page', target_id: this.pageId });
            return;
        }
        if (this.tab === 'comments') {
            void this._commentsOp.run({ wiki_page_id: this.pageId });
            return;
        }
        if (this.tab === 'history') {
            void this._revisions.run({ wiki_page_id: this.pageId });
        }
    }

    private _tabItems() {
        return [
            { value: 'outline', icon: 'list', title: this.t('page.outline') },
            { value: 'backlinks', icon: 'link', title: this.t('page.backlinks') },
            {
                value: 'comments',
                icon: 'chat',
                title: this.t('page.comments'),
                indicator: this._commentItems().length > 0,
            },
            { value: 'history', icon: 'history', title: this.t('history.title') },
        ];
    }

    private _onTabChange(event: CustomEvent<{ value?: string }>) {
        this.tab = missingAsEmpty(event.detail.value);
        this.emit('panel-tab-change', { tab: this.tab });
    }

    override render() {
        return html`
            <div class="head">
                <platform-segmented-control
                    icon-only
                    density="compact"
                    aria-label=${this.t('panel.tabs')}
                    .items=${this._tabItems()}
                    value=${this.tab}
                    @change=${(event: CustomEvent<{ value?: string }>) => this._onTabChange(event)}
                ></platform-segmented-control>
                ${this.embedded
                    ? nothing
                    : html`<button
                          class="close-btn"
                          type="button"
                          data-wiki-panel-close
                          aria-label=${this.t('panel.close')}
                          title=${this.t('panel.close')}
                          @click=${() => this.emit('panel-close', null)}
                      >
                          <platform-icon name="close" size="16"></platform-icon>
                      </button>`}
            </div>
            <div class="body">${this._renderTab()}</div>
        `;
    }

    private _renderTab() {
        if (this.tab === 'outline') {
            return this._renderOutline();
        }
        if (this.tab === 'backlinks') {
            return this._renderBacklinks();
        }
        if (this.tab === 'comments') {
            return this._renderComments();
        }
        if (this.tab === 'history') {
            return this._renderHistory();
        }
        throw new Error(`wiki-page-panel: неизвестная вкладка ${this.tab}`);
    }

    // --- оглавление ---

    private _renderOutline() {
        if (!Array.isArray(this.outline) || this.outline.length === 0) {
            return html`<div class="muted">${this.t('page.outline_empty')}</div>`;
        }
        return html`
            ${this.outline.map((item: WikiOutlineItem) => html`
                <button
                    class="outline-item"
                    type="button"
                    data-wiki-outline-pos=${item.pos}
                    style=${`padding-left:${(item.level - 1) * 10}px`}
                    @click=${() => this.emit('outline-pick', {
                        pos: item.pos,
                        text: item.text,
                        level: item.level,
                    })}
                >${item.text}</button>
            `)}
        `;
    }

    // --- обратные ссылки ---

    private _renderBacklinks() {
        const result = this._backlinks.lastResult;
        if (result === null) {
            return html`<div class="muted">${this.t('page.backlinks_empty')}</div>`;
        }
        const links = itemRecords(result, 'wiki backlinks');
        if (links.length === 0) {
            return html`<div class="muted">${this.t('page.backlinks_empty')}</div>`;
        }
        return html`
            ${links.map((link) => html`
                <a
                    class="backlink"
                    data-wiki-backlink=${link.wiki_page_id}
                    @click=${() => this.navigate('wiki_page', { pageId: missingAsEmpty(link.wiki_page_id) })}
                >${link.title === '' ? this.t('page.untitled') : link.title}</a>
            `)}
        `;
    }

    // --- комментарии ---

    private _commentItems(): Record<string, unknown>[] {
        const result = this._commentsOp.lastResult;
        if (result === null) {
            return [];
        }
        return itemRecords(result, 'wiki comments');
    }

    private async _sendComment(): Promise<void> {
        const body = this._commentDraft.trim();
        if (body === '') {
            return;
        }
        await this._commentCreate.run({ wiki_page_id: this.pageId, body_markdown: body });
        this._commentDraft = '';
        void this._commentsOp.run({ wiki_page_id: this.pageId });
    }

    private async _resolveComment(commentId: string): Promise<void> {
        await this._commentResolve.run({ wiki_comment_id: commentId, resolved: true });
        void this._commentsOp.run({ wiki_page_id: this.pageId });
    }

    private _renderComments() {
        const comments = this._commentItems();
        return html`
            ${comments.length === 0
                ? html`<div class="muted">${this.t('page.comments_empty')}</div>`
                : comments.map((comment: WikiCommentItem) => html`
                      <div class="comment" data-wiki-comment=${comment.wiki_comment_id}>
                          <platform-user-chip
                              user-id=${comment.author_user_id}
                              size="sm"
                          ></platform-user-chip>
                          <div class="comment-body">${comment.body_markdown}</div>
                          ${comment.resolved_at === null
                              ? html`<button
                                    class="ghost-btn"
                                    type="button"
                                    @click=${() => this._resolveComment(missingAsEmpty(comment.wiki_comment_id))}
                                >${this.t('page.comment_resolve')}</button>`
                              : html`<span class="comment-resolved">${this.t('page.comment_resolved')}</span>`}
                          <div class="muted">
                              ${formatPlatformDateTime(new Date(comment.created_at === undefined || comment.created_at === null ? '' : comment.created_at), missingAsEmpty(this._locale.value))}
                          </div>
                      </div>
                  `)}
            <div class="comment-form">
                <textarea
                    class="comment-input"
                    data-canon="composer"
                    aria-label=${this.t('page.comment_placeholder')}
                    placeholder=${this.t('page.comment_placeholder')}
                    .value=${this._commentDraft}
                    @input=${(event: Event) => {
                        const input = event.target;
                        if (!(input instanceof HTMLTextAreaElement)) {
                            throw new Error('wiki-page-panel: comment input required');
                        }
                        this._commentDraft = input.value;
                    }}
                ></textarea>
                <button class="ghost-btn" type="button" data-wiki-comment-send @click=${() => this._sendComment()}>
                    ${this.t('page.comment_send')}
                </button>
            </div>
        `;
    }

    // --- история версий ---

    private _revisionItems(): Record<string, unknown>[] {
        const result = this._revisions.lastResult;
        if (result === null) {
            return [];
        }
        return itemRecords(result, 'wiki revisions');
    }

    private async _selectRevision(revisionId: string): Promise<void> {
        this._selectedRevisionId = revisionId;
        await this._revisionRead.run({ wiki_revision_id: revisionId });
    }

    private async _restoreRevision(): Promise<void> {
        const confirmed = await platformConfirm(this.t('history.restore_confirm_body'), {
            title: this.t('history.restore_confirm_title'),
        });
        if (!confirmed) {
            return;
        }
        await this._revisionRestore.run({ wiki_revision_id: this._selectedRevisionId });
        this._selectedRevisionId = '';
        void this._revisions.run({ wiki_page_id: this.pageId });
        this.emit('revision-restored', null);
    }

    private _renderHistory() {
        const revisions = this._revisionItems();
        if (revisions.length === 0) {
            return html`<div class="muted">${this.t('history.empty')}</div>`;
        }
        return html`
            ${revisions.map((revision) => html`
                <button
                    class="revision ${revision.wiki_revision_id === this._selectedRevisionId ? 'is-selected' : ''}"
                    type="button"
                    data-wiki-revision=${revision.wiki_revision_id}
                    @click=${() => this._selectRevision(missingAsEmpty(revision.wiki_revision_id))}
                >
                    <platform-user-chip user-id=${revision.author_user_id} size="sm"></platform-user-chip>
                    <div class="revision-meta">
                        ${formatPlatformDateTime(new Date(revision.created_at === undefined || revision.created_at === null ? '' : revision.created_at), missingAsEmpty(this._locale.value))}
                    </div>
                </button>
                ${revision.wiki_revision_id === this._selectedRevisionId
                    ? this._renderRevisionDetails()
                    : nothing}
            `)}
        `;
    }

    private _renderRevisionDetails() {
        if (this._revisionRead.busy) {
            return html`<div class="muted"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        const revision = isPlainRecord(this._revisionRead.lastResult) ? this._revisionRead.lastResult : null;
        if (!revision) {
            return nothing;
        }
        return html`
            <div class="revision-actions">
                <platform-button
                    variant="primary"
                    size="sm"
                    data-wiki-revision-restore
                    @click=${() => this._restoreRevision()}
                >${this.t('history.restore')}</platform-button>
                <platform-button
                    variant="ghost"
                    size="sm"
                    data-wiki-revision-compare
                    @click=${() => this.navigate('wiki_page_history', { pageId: this.pageId })}
                >${this.t('history.compare')}</platform-button>
            </div>
            <div class="revision-preview">${revision.text_markdown}</div>
        `;
    }
}

customElements.define('wiki-page-panel', WikiPagePanel);
