/**
 * Страница базы знаний — «лист бумаги» с редактором и боковой панелью.
 *
 * Правки уходят на сервер с задержкой: редактор шлёт событие на каждое
 * нажатие, а сохранять на каждый символ значит и грузить сеть, и плодить
 * версии. Индикатор состояния показывает, что происходит.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-emoji-picker.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/platform-rich-editor.js';
import '@platform/lib/components/platform-user-chip.js';

const SAVE_DEBOUNCE_MS = 900;

/** Состояние строки сохранения. */
const SAVE_IDLE = 'idle';
const SAVE_PENDING = 'pending';
const SAVE_DONE = 'done';
const SAVE_FAILED = 'failed';

export class WikiPageView extends PlatformPage {
    static i18nNamespace = 'wiki';

    static properties = {
        pageId: { type: String, attribute: 'page-id' },
        _page: { state: true },
        _saveState: { state: true },
        _outline: { state: true },
        _iconAnchor: { state: true },
        _menuAnchor: { state: true },
        _commentDraft: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                height: 100%;
                overflow: hidden;
            }

            .layout {
                display: grid;
                grid-template-columns: minmax(0, 1fr) var(--wiki-outline-width);
                height: 100%;
                min-height: 0;
            }

            .scroll {
                min-width: 0;
                overflow-y: auto;
            }

            .cover {
                position: relative;
                height: var(--wiki-cover-height);
                background-size: cover;
                background-position: center;
            }

            .cover-actions {
                position: absolute;
                right: var(--space-4);
                bottom: var(--space-3);
                display: flex;
                gap: var(--space-2);
            }

            .paper {
                max-width: var(--wiki-page-max-width);
                margin: 0 auto;
                padding: var(--space-6) var(--space-6) var(--space-10);
            }

            .head-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
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

            .spacer {
                flex: 1;
            }

            .outline-btn {
                display: none;
            }

            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 64px;
                height: 64px;
                margin-bottom: var(--space-2);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                font-size: 52px;
                line-height: 1;
                cursor: pointer;
            }

            .icon-btn:hover {
                background: var(--wiki-surface-muted);
            }

            .title-input {
                width: 100%;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: 40px;
                font-weight: var(--font-bold);
                line-height: 1.15;
                letter-spacing: -0.02em;
                outline: none;
            }

            .title-input::placeholder {
                color: var(--text-disabled);
            }

            .save-state {
                min-height: 18px;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .save-state[data-state='failed'] {
                color: var(--error);
            }

            .aside {
                min-width: 0;
                padding: var(--space-6) var(--space-4);
                border-left: 1px solid var(--glass-border-subtle);
                overflow-y: auto;
            }

            .aside-title {
                margin-bottom: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
            }

            .aside-section + .aside-section {
                margin-top: var(--space-6);
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

            .muted {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .state {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
            }

            @media (max-width: 1100px) {
                .layout {
                    grid-template-columns: minmax(0, 1fr);
                }
                .aside {
                    display: none;
                }
            }

            @media (max-width: 1100px) {
                /* Правая колонка скрыта — оглавление открывается снизу. */
                .outline-btn {
                    display: inline-flex;
                }
            }

            @media (max-width: 767px) {
                .paper {
                    padding: var(--space-4) var(--space-4) var(--space-10);
                }
                .title-input {
                    font-size: 28px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.pageId = '';
        this._page = null;
        this._saveState = SAVE_IDLE;
        this._outline = [];
        this._iconAnchor = null;
        this._menuAnchor = null;
        this._commentDraft = '';
        this._saveTimer = null;
        this._pendingContent = null;
        this._pendingTitle = null;

        this._read = this.useOp('wiki/page_read');
        this._save = this.useOp('wiki/page_save');
        this._properties = this.useOp('wiki/page_properties');
        this._deletePage = this.useOp('wiki/page_delete');
        this._backlinks = this.useOp('wiki/backlinks');
        this._comments = this.useOp('wiki/comments');
        this._commentCreate = this.useOp('wiki/comment_create');
        this._commentResolve = this.useOp('wiki/comment_resolve');
        this._search = this.useOp('wiki/search');
        this._pages = this.useResource('wiki/pages');
        this._locale = this.select((state) => state.i18n.locale);
        this._mentionProvider = this._mentionProvider.bind(this);
        this._openOutlineSheet = this._openOutlineSheet.bind(this);
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('pageId') && this.pageId !== '') {
            void this._loadPage();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._flushPendingSave();
    }

    async _loadPage() {
        this._page = null;
        this._outline = [];
        const page = await this._read.run({ wiki_page_id: this.pageId });
        this._page = page;
        void this._backlinks.run({ wiki_page_id: this.pageId });
        void this._comments.run({ wiki_page_id: this.pageId });
    }

    // --- сохранение ---

    _scheduleSave() {
        this._saveState = SAVE_PENDING;
        if (this._saveTimer !== null) {
            clearTimeout(this._saveTimer);
        }
        this._saveTimer = window.setTimeout(() => {
            this._saveTimer = null;
            void this._commitSave();
        }, SAVE_DEBOUNCE_MS);
    }

    /** Досохранить при уходе со страницы, иначе последние правки потеряются. */
    _flushPendingSave() {
        if (this._saveTimer === null) {
            return;
        }
        clearTimeout(this._saveTimer);
        this._saveTimer = null;
        void this._commitSave();
    }

    async _commitSave() {
        if (this._page === null) {
            return;
        }
        const content = this._pendingContent === null ? this._page.content : this._pendingContent;
        const title = this._pendingTitle === null ? this._page.title : this._pendingTitle;
        try {
            const saved = await this._save.run({
                wiki_page_id: this.pageId,
                content,
                title,
                create_revision: true,
            });
            this._page = saved;
            this._pendingContent = null;
            this._pendingTitle = null;
            this._saveState = SAVE_DONE;
            void this._pages.load();
        } catch (error) {
            this._saveState = SAVE_FAILED;
            throw error;
        }
    }

    _onEditorChange(event) {
        this._pendingContent = event.detail.content;
        this._scheduleSave();
        this._refreshOutline();
    }

    _onTitleInput(event) {
        this._pendingTitle = event.target.value;
        this._scheduleSave();
    }

    _refreshOutline() {
        const editor = this.renderRoot.querySelector('platform-rich-editor');
        this._outline = editor ? editor.getOutline() : [];
    }

    // --- иконка, обложка, меню ---

    _onIconSelect(event) {
        void this._properties.run({ wiki_page_id: this.pageId, icon: event.detail.emoji });
        this._page = { ...this._page, icon: event.detail.emoji };
        this._iconAnchor = null;
        void this._pages.load();
    }

    _onIconClear() {
        void this._properties.run({ wiki_page_id: this.pageId, icon: '' });
        this._page = { ...this._page, icon: '' };
        this._iconAnchor = null;
        void this._pages.load();
    }

    _pageMenuItems() {
        const hasCover = this._page.cover_url !== '';
        return [
            { id: 'history', label: this.t('page.history_link'), icon: 'history' },
            { id: 'access', label: this.t('tree_menu.access'), icon: 'lock' },
            { id: 'move', label: this.t('tree_menu.move'), icon: 'move' },
            { id: 'sep', kind: 'separator' },
            {
                id: hasCover ? 'remove_cover' : 'add_cover',
                label: hasCover ? this.t('page.remove_cover') : this.t('page.add_cover'),
                icon: 'image',
            },
            { id: 'sep2', kind: 'separator' },
            { id: 'delete', label: this.t('tree_menu.delete'), icon: 'trash', danger: true },
        ];
    }

    async _onPageMenuSelect(event) {
        const action = event.detail.id;
        this._menuAnchor = null;
        if (action === 'history') {
            this.navigate('wiki_page_history', { pageId: this.pageId });
            return;
        }
        if (action === 'access') {
            this.openModal('wiki.page_access', { pageId: this.pageId });
            return;
        }
        if (action === 'move') {
            this.openModal('wiki.move_page', { pageId: this.pageId });
            return;
        }
        if (action === 'add_cover') {
            const url = window.prompt(this.t('page.cover_url_prompt'));
            if (url === null || url.trim() === '') {
                return;
            }
            await this._properties.run({ wiki_page_id: this.pageId, cover_url: url.trim() });
            this._page = { ...this._page, cover_url: url.trim() };
            return;
        }
        if (action === 'remove_cover') {
            await this._properties.run({ wiki_page_id: this.pageId, cover_url: '' });
            this._page = { ...this._page, cover_url: '' };
            return;
        }
        if (action === 'delete') {
            const confirmed = await platformConfirm({
                title: this.t('page.delete_confirm_title'),
                message: this.t('page.delete_confirm_body'),
                danger: true,
            });
            if (!confirmed) {
                return;
            }
            await this._deletePage.run({ wiki_page_id: this.pageId });
            await this._pages.load();
            this.navigate('wiki_home', {});
            return;
        }
        throw new Error(`wiki-page-view: неизвестное действие страницы ${action}`);
    }

    // --- упоминания ---

    /** Источники упоминаний: страницы базы знаний и участники компании. */
    async _mentionProvider(query) {
        const trimmed = query.trim();
        const pages = this._pages.items
            .filter((page) => trimmed === '' || page.title.toLowerCase().includes(trimmed.toLowerCase()))
            .slice(0, 6)
            .map((page) => ({
                id: page.wiki_page_id,
                kind: 'wiki_page',
                label: page.title === '' ? this.t('page.untitled') : page.title,
            }));
        if (trimmed === '') {
            return pages;
        }
        const found = await this._search.run({ query: trimmed, mode: 'lexical', limit: 6 });
        const hits = Array.isArray(found.items) ? found.items : [];
        const extra = hits
            .filter((hit) => !pages.some((page) => page.id === hit.wiki_page_id))
            .map((hit) => ({ id: hit.wiki_page_id, kind: 'wiki_page', label: hit.title }));
        return [...pages, ...extra];
    }

    // --- комментарии ---

    async _sendComment() {
        const body = this._commentDraft.trim();
        if (body === '') {
            return;
        }
        await this._commentCreate.run({ wiki_page_id: this.pageId, body_markdown: body });
        this._commentDraft = '';
        void this._comments.run({ wiki_page_id: this.pageId });
    }

    async _resolveComment(commentId) {
        await this._commentResolve.run({ wiki_comment_id: commentId, resolved: true });
        void this._comments.run({ wiki_page_id: this.pageId });
    }

    render() {
        if (this._page === null) {
            return html`<div class="state">
                ${this._read.busy
                    ? html`<glass-spinner size="sm"></glass-spinner>`
                    : this.t('page.not_found')}
            </div>`;
        }

        return html`
            <div class="layout">
                <div class="scroll">
                    ${this._page.cover_url !== ''
                        ? html`<div class="cover" style=${`background-image:url(${this._page.cover_url})`}></div>`
                        : nothing}
                    <div class="paper">
                        ${this._renderHeadActions()}
                        ${this._renderIcon()}
                        <input
                            class="title-input"
                            type="text"
                            data-canon="inline-edit"
                            data-wiki-title
                            aria-label=${this.t('page.title_placeholder')}
                            placeholder=${this.t('page.title_placeholder')}
                            .value=${this._page.title}
                            @input=${this._onTitleInput}
                        />
                        <div class="save-state" data-state=${this._saveState}>${this._saveLabel()}</div>
                        <platform-rich-editor
                            .value=${this._page.content}
                            .mentionProvider=${this._mentionProvider}
                            placeholder=${this.t('page.title_placeholder')}
                            @change=${this._onEditorChange}
                        ></platform-rich-editor>
                    </div>
                </div>
                <aside class="aside">
                    ${this._renderOutline()}
                    ${this._renderBacklinks()}
                    ${this._renderComments()}
                </aside>
            </div>
            ${this._renderIconPopover()}
            ${this._renderPageMenu()}
        `;
    }

    _saveLabel() {
        if (this._saveState === SAVE_PENDING) return this.t('page.saving');
        if (this._saveState === SAVE_DONE) return this.t('page.saved');
        if (this._saveState === SAVE_FAILED) return this.t('page.save_failed');
        return '';
    }

    _renderHeadActions() {
        return html`
            <div class="head-actions">
                <platform-breadcrumbs
                    current-label=${this._page.title === '' ? this.t('page.untitled') : this._page.title}
                ></platform-breadcrumbs>
                <span class="spacer"></span>
                <span>${this._page.is_published ? this.t('page.published') : this.t('page.draft')}</span>
                <button
                    class="ghost-btn outline-btn"
                    type="button"
                    data-wiki-outline-sheet
                    aria-label=${this.t('page.outline')}
                    @click=${this._openOutlineSheet}
                >
                    <platform-icon name="list" size="16"></platform-icon>
                </button>
                <button
                    class="ghost-btn"
                    type="button"
                    data-wiki-page-menu
                    aria-label=${this.t('tree_menu.open')}
                    @click=${(event) => { this._menuAnchor = event.currentTarget; }}
                >
                    <platform-icon name="more-horizontal" size="16"></platform-icon>
                </button>
            </div>
        `;
    }

    _renderIcon() {
        return html`
            <button
                class="icon-btn"
                type="button"
                data-wiki-icon
                title=${this._page.icon === '' ? this.t('page.add_icon') : this.t('page.change_icon')}
                aria-label=${this._page.icon === '' ? this.t('page.add_icon') : this.t('page.change_icon')}
                @click=${(event) => { this._iconAnchor = event.currentTarget; }}
            >
                ${this._page.icon === ''
                    ? html`<platform-icon name="smile" size="24"></platform-icon>`
                    : this._page.icon}
            </button>
        `;
    }

    _renderIconPopover() {
        return html`
            <platform-popover
                trigger="manual"
                role="dialog"
                placement="bottom-start"
                offset="6"
                .anchor=${this._iconAnchor}
                ?open=${this._iconAnchor !== null}
                @popover-dismiss=${() => { this._iconAnchor = null; }}
            >
                ${this._iconAnchor !== null
                    ? html`<platform-emoji-picker
                          value=${this._page.icon}
                          @emoji-select=${this._onIconSelect}
                          @emoji-clear=${this._onIconClear}
                      ></platform-emoji-picker>`
                    : nothing}
            </platform-popover>
        `;
    }

    _renderPageMenu() {
        return html`
            <platform-popover
                trigger="manual"
                role="menu"
                placement="bottom-end"
                offset="4"
                .anchor=${this._menuAnchor}
                ?open=${this._menuAnchor !== null}
                @popover-dismiss=${() => { this._menuAnchor = null; }}
            >
                ${this._menuAnchor !== null
                    ? html`<platform-menu
                          compact
                          .items=${this._pageMenuItems()}
                          @menu-select=${this._onPageMenuSelect}
                      ></platform-menu>`
                    : nothing}
            </platform-popover>
        `;
    }

    _renderOutline() {
        return html`
            <section class="aside-section">
                <div class="aside-title">${this.t('page.outline')}</div>
                ${this._outline.length === 0
                    ? html`<div class="muted">${this.t('page.outline_empty')}</div>`
                    : this._outline.map((item) => html`
                          <button
                              class="outline-item"
                              type="button"
                              style=${`padding-left:${(item.level - 1) * 10}px`}
                              @click=${() => this._scrollToHeading(item.pos)}
                          >${item.text}</button>
                      `)}
            </section>
        `;
    }

    _openOutlineSheet() {
        this._refreshOutline();
        // Прокрутку делает страница: только у неё есть ссылка на редактор.
        this.openBottomSheet('wiki.outline', {
            outline: this._outline,
            onPick: (pos) => this._scrollToHeading(pos),
        });
    }

    _scrollToHeading(pos) {
        this.renderRoot.querySelector('platform-rich-editor').scrollToPosition(pos);
    }

    _renderBacklinks() {
        const items = this._backlinks.state.items;
        const links = Array.isArray(items) ? items : [];
        return html`
            <section class="aside-section">
                <div class="aside-title">${this.t('page.backlinks')}</div>
                ${links.length === 0
                    ? html`<div class="muted">${this.t('page.backlinks_empty')}</div>`
                    : links.map((link) => html`
                          <a
                              class="backlink"
                              data-wiki-backlink=${link.wiki_page_id}
                              @click=${() => this.navigate('wiki_page', { pageId: link.wiki_page_id })}
                          >${link.title === '' ? this.t('page.untitled') : link.title}</a>
                      `)}
            </section>
        `;
    }

    _renderComments() {
        const items = this._comments.state.items;
        const comments = Array.isArray(items) ? items : [];
        return html`
            <section class="aside-section">
                <div class="aside-title">${this.t('page.comments')}</div>
                ${comments.length === 0
                    ? html`<div class="muted">${this.t('page.comments_empty')}</div>`
                    : comments.map((comment) => html`
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
                                        @click=${() => this._resolveComment(comment.wiki_comment_id)}
                                    >${this.t('page.comment_resolve')}</button>`
                                  : html`<span class="comment-resolved">${this.t('page.comment_resolved')}</span>`}
                              <div class="muted">
                                  ${formatPlatformDateTime(new Date(comment.created_at), this._locale.value)}
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
                        @input=${(event) => { this._commentDraft = event.target.value; }}
                    ></textarea>
                    <button class="ghost-btn" type="button" data-wiki-comment-send @click=${this._sendComment}>
                        ${this.t('page.comment_send')}
                    </button>
                </div>
            </section>
        `;
    }
}

customElements.define('wiki-page-view', WikiPageView);
