/**
 * Страница базы знаний — «лист бумаги» с редактором и боковой панелью.
 *
 * Правки уходят на сервер с задержкой: редактор шлёт событие на каждое
 * нажатие, а сохранять на каждый символ значит и грузить сеть, и плодить
 * версии. Индикатор состояния показывает, что происходит.
 *
 * Шапка с путём и действиями идёт по всей ширине рабочей области и липнет к
 * верху при прокрутке; колонка текста при этом остаётся по центру.
 *
 * Боковая панель (оглавление, ссылки, комментарии, история) по умолчанию
 * закрыта: ширина колонки текста важнее постоянно висящих списков. Открытое
 * состояние и выбранная вкладка запоминаются, как ширина дерева.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { buildWikiPageFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { buildPlatformFileDownloadUrl } from '@platform/lib/utils/platform-files-url.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-emoji-picker.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/platform-rich-editor.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';
import { WIKI_PANEL_TABS } from '../components/wiki-page-panel.js';
import '../components/wiki-page-panel.js';

const SAVE_DEBOUNCE_MS = 900;

const PANEL_STORAGE_KEY = platformStorageKey('wiki', 'page.panel');
const PANEL_DEFAULT_TAB = 'outline';

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
        _panelOpen: { state: true },
        _panelTab: { state: true },
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
                display: flex;
                height: 100%;
                min-height: 0;
            }

            .scroll {
                flex: 1;
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
                opacity: 0;
                transition: var(--motion-transition-interactive, opacity 120ms ease);
            }

            .cover:hover .cover-actions,
            .cover:focus-within .cover-actions {
                opacity: 1;
            }

            /* Боковое поле равно --wiki-block-gutter: в левом живут кнопки блока
               редактора, правое зеркалит его, чтобы текст стоял по центру. */
            .paper {
                max-width: var(--wiki-page-max-width);
                margin: 0 auto;
                padding: var(--space-4) var(--wiki-block-gutter) var(--space-10);
            }

            /* Полная ширина — свойство страницы: колонка занимает всю рабочую
               область, боковые поля остаются равными полосе кнопок блока. */
            .paper[data-full-width] {
                max-width: none;
            }

            /* Шапка занимает всю ширину рабочей области, а не колонку текста:
               путь читается от левого края, действия прижаты к правому. При
               прокрутке остаётся на месте — иначе с длинной страницы не выйти. */
            .topbar {
                position: sticky;
                top: 0;
                z-index: 3;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                background: var(--glass-tint-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
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

            .edited {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 3px var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                font-family: inherit;
                font-size: var(--text-xs);
                white-space: nowrap;
                cursor: pointer;
            }

            .edited:hover {
                background: var(--wiki-surface-muted);
                color: var(--text-primary);
            }

            @media (max-width: 767px) {
                .edited {
                    display: none;
                }
            }

            .title-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
                min-width: 0;
            }

            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                width: 104px;
                height: 104px;
                margin: 0;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                font-size: 80px;
                line-height: 1;
                cursor: pointer;
            }

            .icon-btn:hover {
                background: var(--wiki-surface-muted);
            }

            /* Специфичность выше :host input { font: inherit } из baseStyles —
               иначе shorthand сбрасывает размер и вес до body. */
            :host input.title-input {
                flex: 1;
                min-width: 0;
                width: auto;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: 48px;
                font-weight: 700;
                line-height: 1.12;
                letter-spacing: -0.03em;
                outline: none;
            }

            :host input.title-input::placeholder {
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

            wiki-page-panel {
                flex: 0 0 var(--wiki-outline-width);
                border-left: 1px solid var(--glass-border-subtle);
            }

            .state {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
            }

            /* Узкий экран: панель не отнимает ширину у текста, вкладки уходят
               в bottom-sheet по кнопке в шапке. */
            @media (max-width: 1100px) {
                wiki-page-panel {
                    display: none;
                }
            }

            @media (max-width: 767px) {
                .topbar {
                    padding: var(--space-2);
                }
                .paper {
                    padding: var(--space-3) var(--space-4) var(--space-10);
                }
                :host input.title-input {
                    font-size: 32px;
                }
                .icon-btn {
                    width: 80px;
                    height: 80px;
                    font-size: 56px;
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
        this._panelOpen = false;
        this._panelTab = PANEL_DEFAULT_TAB;
        this._restorePanelState();
        this._saveTimer = null;
        this._pendingContent = null;
        this._pendingTitle = null;

        this._read = this.useOp('wiki/page_read');
        this._save = this.useOp('wiki/page_save');
        this._properties = this.useOp('wiki/page_properties');
        this._deletePage = this.useOp('wiki/page_delete');
        this._search = this.useOp('wiki/search');
        this._markdownImport = this.useOp('wiki/page_markdown_import');
        this._markdownParse = this.useOp('wiki/markdown_parse');
        this._pages = this.useResource('wiki/pages');
        this._locale = this.select((state) => state.i18n.locale);
        this._mentionProvider = this._mentionProvider.bind(this);
        this._openPanelSheet = this._openPanelSheet.bind(this);
        this._parseMarkdown = this._parseMarkdown.bind(this);
        this._onMarkdownFileDrop = this._onMarkdownFileDrop.bind(this);
        this._onMarkdownFileSelected = this._onMarkdownFileSelected.bind(this);
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => {
            if (this.pageId !== '') {
                void this._loadPage();
            }
        });
        this._routerSearchSel = this.select((s) => s.router.search);
        this._accessModalOpened = false;
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('pageId') && this.pageId !== '') {
            const previousPageId = changed.get('pageId');
            if (typeof previousPageId === 'string' && previousPageId !== '') {
                // Досохранение прежней страницы: this.pageId уже новый,
                // а pending-правки принадлежат старому id.
                this._flushPendingSave(previousPageId);
            }
            this._accessModalOpened = false;
            void this._loadPage();
        }
        this._maybeOpenAccessModal();
    }

    _maybeOpenAccessModal() {
        if (this._accessModalOpened) {
            return;
        }
        if (this.pageId === '') {
            return;
        }
        const search = this._routerSearchSel.value;
        const raw = typeof search === 'string' ? search : '';
        const query = raw.startsWith('?') ? raw.slice(1) : raw;
        if (new URLSearchParams(query).get('access') !== '1') {
            return;
        }
        this._accessModalOpened = true;
        this.openModal('wiki.page_access', { pageId: this.pageId });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._flushPendingSave();
    }

    async _loadPage() {
        const pageId = this.pageId;
        if (pageId === '') {
            return;
        }
        this._page = null;
        this._outline = [];
        this._pendingContent = null;
        this._pendingTitle = null;
        this._saveState = SAVE_IDLE;
        const response = await this._read.run({ wiki_page_id: pageId });
        if (this.pageId !== pageId) {
            return;
        }
        // Ответ команды — WikiPageResponse { page, can_edit, can_admin }:
        // на экране живёт сама WikiPage.
        this._page = response === null ? null : response.page;
        await this.updateComplete;
        await this._refreshOutlineWhenEditorReady();
    }

    async _refreshOutlineWhenEditorReady() {
        for (let attempt = 0; attempt < 60; attempt += 1) {
            const editor = this.renderRoot.querySelector('platform-rich-editor');
            if (editor && editor.isReady) {
                this._outline = editor.getOutline();
                return;
            }
            await new Promise((resolve) => {
                window.setTimeout(resolve, 20);
            });
        }
        this._refreshOutline();
    }

    // --- боковая панель ---

    /** Раскладка панели переживает переход между страницами и перезагрузку. */
    _restorePanelState() {
        const stored = window.localStorage.getItem(PANEL_STORAGE_KEY);
        if (stored === null) {
            return;
        }
        const parsed = JSON.parse(stored);
        if (typeof parsed.open !== 'boolean' || !WIKI_PANEL_TABS.includes(parsed.tab)) {
            throw new Error(`wiki-page-view: битое состояние панели ${stored}`);
        }
        this._panelOpen = parsed.open;
        this._panelTab = parsed.tab;
    }

    _persistPanelState() {
        window.localStorage.setItem(
            PANEL_STORAGE_KEY,
            JSON.stringify({ open: this._panelOpen, tab: this._panelTab }),
        );
    }

    /** Кнопка в шапке: та же вкладка закрывает панель, другая переключает. */
    _togglePanel(tab) {
        if (window.matchMedia('(max-width: 1100px)').matches) {
            this._panelTab = tab;
            this._persistPanelState();
            this._openPanelSheet();
            return;
        }
        this._panelOpen = !(this._panelOpen && this._panelTab === tab);
        this._panelTab = tab;
        this._persistPanelState();
        this._refreshOutline();
    }

    _closePanel() {
        this._panelOpen = false;
        this._persistPanelState();
    }

    _onPanelTabChange(event) {
        this._panelTab = event.detail.tab;
        this._persistPanelState();
    }

    _openPanelSheet() {
        this._refreshOutline();
        // Прокрутку делает страница: только у неё есть ссылка на редактор.
        this.openBottomSheet('wiki.outline', {
            pageId: this.pageId,
            tab: this._panelTab,
            outline: this._outline,
            onPick: (item) => this._scrollToHeading(item),
            onTabChange: (tab) => {
                this._panelTab = tab;
                this._persistPanelState();
            },
        });
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
    _flushPendingSave(pageId = this.pageId) {
        if (this._saveTimer === null) {
            return;
        }
        clearTimeout(this._saveTimer);
        this._saveTimer = null;
        void this._commitSave(pageId);
    }

    async _commitSave(pageId = this.pageId) {
        if (this._page === null) {
            this._saveState = SAVE_FAILED;
            return;
        }
        const content = this._pendingContent === null ? this._page.content : this._pendingContent;
        const title = this._pendingTitle === null ? this._page.title : this._pendingTitle;
        const saved = await this._save.run({
            wiki_page_id: pageId,
            content,
            title,
            create_revision: true,
        });
        // Неудача резолвится в null (контракт OpController).
        if (saved === null) {
            if (pageId !== this.pageId) {
                // Досохранение прежней страницы: индикатор относится к новому
                // экрану, о несохранённых правках сообщаем тостом.
                this.toast('page.save_failed', { type: 'error' });
                return;
            }
            // Правки остаются в pending, страница не подменяется пустотой.
            this._saveState = SAVE_FAILED;
            return;
        }
        if (pageId !== this.pageId) {
            // Досохранение прежней страницы при уходе: экран уже на другой,
            // ответ трогать нельзя — только дерево обновляется.
            void this._pages.load();
            return;
        }
        // Pending сбрасывается только если в нём та самая правка: напечатанное
        // за время полёта команды уже ждёт следующего таймера.
        if (this._pendingContent === content) {
            this._pendingContent = null;
        }
        if (this._pendingTitle === title) {
            this._pendingTitle = null;
        }
        // Ответ команды — WikiPageResponse { page, can_edit, can_admin };
        // свежие pending-правки поверх сохранённого снимка не затираются.
        this._page = {
            ...saved.page,
            content: this._pendingContent === null ? saved.page.content : this._pendingContent,
            title: this._pendingTitle === null ? saved.page.title : this._pendingTitle,
        };
        if (this._pendingContent === null && this._pendingTitle === null) {
            this._saveState = SAVE_DONE;
        }
        this._refreshOutline();
        void this._pages.load();
    }

    _onEditorChange(event) {
        // Редактор в light DOM: native `change` с select языка / file input
        // тоже всплывает сюда без detail — их игнорируем.
        const detail = event.detail;
        if (detail === null || typeof detail !== 'object' || !('content' in detail)) {
            return;
        }
        const content = detail.content;
        if (content === null || typeof content !== 'object') {
            throw new Error('wiki-page-view: editor change without document content');
        }
        this._pendingContent = content;
        // Страница перерисовывается от индикатора сохранения и оглавления и при
        // этом заново связывает `.value` редактора. Без синхронизации туда
        // уезжал бы документ до правки, и набранный символ терялся.
        this._page = { ...this._page, content };
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
            { id: 'move', label: this.t('tree_menu.move'), icon: 'swap-horiz' },
            { id: 'sep_md', kind: 'separator' },
            { id: 'import_markdown', label: this.t('page.import_markdown'), icon: 'import' },
            { id: 'export_markdown', label: this.t('page.export_markdown'), icon: 'download' },
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
        if (action === 'import_markdown') {
            this._openMarkdownPicker();
            return;
        }
        if (action === 'export_markdown') {
            this._downloadMarkdown();
            return;
        }
        if (action === 'add_cover') {
            this._openCoverPicker();
            return;
        }
        if (action === 'remove_cover') {
            await this._removeCover();
            return;
        }
        if (action === 'delete') {
            const confirmed = await platformConfirm(this.t('page.delete_confirm_body'), {
                title: this.t('page.delete_confirm_title'),
                variant: 'danger',
                confirmVariant: 'danger',
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

    _wikiFileCreateSpec(metadata) {
        if (!this._page || typeof this._page.namespace !== 'string' || this._page.namespace.length === 0) {
            throw new Error('wiki-page-view: page.namespace required for file create');
        }
        if (typeof this.pageId !== 'string' || this.pageId.length === 0) {
            throw new Error('wiki-page-view: pageId required for file create');
        }
        return buildWikiPageFileCreateSpecJson({
            wikiPageId: this.pageId,
            namespaceId: this._page.namespace,
            metadata,
        });
    }

    _openFilePicker({ acceptMimePrefix, metadata, onSelect }) {
        this.openModal('platform.file_picker', {
            acceptMimePrefix,
            uploadOpName: 'platform/file_create',
            uploadSpec: this._wikiFileCreateSpec(metadata),
            catalogsOpName: 'office/catalogs_list',
            documentsOpName: 'office/documents_list',
            searchOpName: 'office/documents_search',
            onSelect,
        });
    }

    _openCoverPicker() {
        this._openFilePicker({
            acceptMimePrefix: 'image/',
            metadata: { purpose: 'wiki_cover' },
            onSelect: (file) => {
                void this._applyCover(file);
            },
        });
    }

    async _applyCover(file) {
        if (!file || typeof file.file_id !== 'string' || file.file_id.length === 0) {
            throw new Error('wiki-page-view: cover file_id required');
        }
        const coverUrl = buildPlatformFileDownloadUrl(file.file_id);
        await this._properties.run({ wiki_page_id: this.pageId, cover_url: coverUrl });
        this._page = { ...this._page, cover_url: coverUrl };
    }

    async _removeCover() {
        await this._properties.run({ wiki_page_id: this.pageId, cover_url: '' });
        this._page = { ...this._page, cover_url: '' };
    }

    _onEditorFilePickRequested(event) {
        const kind = event.detail && event.detail.kind;
        if (kind !== 'image' && kind !== 'file') {
            throw new Error(`wiki-page-view: unknown file pick kind ${String(kind)}`);
        }
        this._openFilePicker({
            acceptMimePrefix: kind === 'image' ? 'image/' : '',
            metadata: { purpose: kind === 'image' ? 'wiki_image' : 'wiki_file' },
            onSelect: (file) => {
                this._insertPickedEditorFile(kind, file);
            },
        });
    }

    _insertPickedEditorFile(kind, file) {
        const editor = this.renderRoot.querySelector('platform-rich-editor');
        if (!editor) {
            throw new Error('wiki-page-view: rich editor missing');
        }
        if (kind === 'image') {
            editor.insertImage({
                fileId: file.file_id,
                src: buildPlatformFileDownloadUrl(file.file_id),
                alt: file.original_name,
            });
            return;
        }
        editor.insertPlatformFile({
            fileId: file.file_id,
            originalName: file.original_name,
            contentType: file.content_type,
        });
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
        if (found === null) {
            return pages;
        }
        if (typeof found !== 'object' || !Array.isArray(found.items)) {
            throw new Error('wiki mention search: result.items required');
        }
        const hits = found.items;
        const extra = hits
            .filter((hit) => !pages.some((page) => page.id === hit.wiki_page_id))
            .map((hit) => ({ id: hit.wiki_page_id, kind: 'wiki_page', label: hit.title }));
        return [...pages, ...extra];
    }

    // --- markdown ---

    _openMarkdownPicker() {
        const input = this.renderRoot.querySelector('[data-wiki-markdown-input]');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('wiki-page-view: markdown file input missing');
        }
        input.value = '';
        input.click();
    }

    async _onMarkdownFileSelected(event) {
        const input = event.target;
        const file = input.files && input.files.length > 0 ? input.files[0] : null;
        if (file === null) {
            return;
        }
        await this._importMarkdownFile(file);
    }

    /**
     * Импорт заменяет содержимое страницы целиком, поэтому у непустой страницы
     * спрашивается подтверждение: отменить импорт можно только через историю
     * версий, а это неочевидно.
     */
    async _importMarkdownFile(file) {
        const markdown = await file.text();
        if (markdown.trim() === '') {
            this.toast('toast.markdown.empty_file', { type: 'warning' });
            return;
        }
        if (this._hasContent()) {
            const confirmed = await platformConfirm(
                this.t('page.import_confirm_body', { name: file.name }),
                { title: this.t('page.import_confirm_title') },
            );
            if (!confirmed) {
                return;
            }
        }

        const result = await this._markdownImport.run({
            wiki_page_id: this.pageId,
            markdown,
            apply_front_matter: true,
        });
        if (result === null) {
            return;
        }
        this._page = result.page;
        this._pendingContent = null;
        this._pendingTitle = null;
        this._saveState = SAVE_IDLE;
        void this._pages.load();
        this._refreshOutline();
        if (Array.isArray(result.notices) && result.notices.length > 0) {
            this.openModal('wiki.import_report', { notices: result.notices });
        }
    }

    /** Есть ли на странице что-то, кроме единственного пустого абзаца. */
    _hasContent() {
        const content = this._page.content;
        if (!content || !Array.isArray(content.content)) {
            return false;
        }
        if (content.content.length !== 1) {
            return content.content.length > 1;
        }
        const only = content.content[0];
        return only.type !== 'paragraph' || Array.isArray(only.content) && only.content.length > 0;
    }

    /**
     * Выгрузка идёт обычной ссылкой на роут файла: это не изменение состояния,
     * а браузеру нужны его же заголовки вложения.
     */
    _downloadMarkdown() {
        const anchor = document.createElement('a');
        anchor.href = `/wiki/api/v1/pages/${encodeURIComponent(this.pageId)}/markdown/file`;
        anchor.download = '';
        anchor.click();
    }

    /** Разбор markdown живёт на сервере; редактор получает только эту функцию. */
    async _parseMarkdown(markdown) {
        const result = await this._markdownParse.run({ markdown });
        return result === null ? null : result.document;
    }

    _onMarkdownFileDrop(event) {
        void this._importMarkdownFile(event.detail.file);
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
                <div class="scroll" data-wiki-page-scroll>
                    ${this._renderTopbar()}
                    ${this._page.cover_url !== ''
                        ? html`<div class="cover" style=${`background-image:url(${this._page.cover_url})`}>
                            <div class="cover-actions">
                                <platform-button
                                    variant="secondary"
                                    size="sm"
                                    icon-only
                                    title=${this.t('page.change_cover')}
                                    aria-label=${this.t('page.change_cover')}
                                    @click=${() => this._openCoverPicker()}
                                >
                                    <platform-icon name="image" size="16"></platform-icon>
                                </platform-button>
                                <platform-button
                                    variant="secondary"
                                    size="sm"
                                    icon-only
                                    title=${this.t('page.remove_cover')}
                                    aria-label=${this.t('page.remove_cover')}
                                    @click=${() => void this._removeCover()}
                                >
                                    <platform-icon name="trash" size="16"></platform-icon>
                                </platform-button>
                            </div>
                        </div>`
                        : nothing}
                    <div class="paper" ?data-full-width=${this._page.is_full_width}>
                        <div class="title-row">
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
                        </div>
                        <div class="save-state" data-state=${this._saveState}>${this._saveLabel()}</div>
                        <platform-rich-editor
                            .value=${this._page.content}
                            .mentionProvider=${this._mentionProvider}
                            .markdownParser=${this._parseMarkdown}
                            placeholder=${this.t('editor.placeholder', null, 'platform')}
                            @change=${this._onEditorChange}
                            @markdown-file-drop=${this._onMarkdownFileDrop}
                            @file-pick-requested=${this._onEditorFilePickRequested}
                        ></platform-rich-editor>
                        <input
                            type="file"
                            hidden
                            data-wiki-markdown-input
                            accept=".md,.markdown,text/markdown"
                            @change=${this._onMarkdownFileSelected}
                        />
                    </div>
                </div>
                ${this._panelOpen
                    ? html`<wiki-page-panel
                          page-id=${this.pageId}
                          tab=${this._panelTab}
                          .outline=${this._outline}
                          @panel-close=${this._closePanel}
                          @panel-tab-change=${this._onPanelTabChange}
                          @outline-pick=${(event) => this._scrollToHeading(event.detail)}
                          @revision-restored=${() => this._loadPage()}
                      ></wiki-page-panel>`
                    : nothing}
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

    _renderTopbar() {
        return html`
            <div class="topbar">
                <platform-breadcrumbs
                    current-label=${this._page.title === '' ? this.t('page.untitled') : this._page.title}
                    .trail=${this._breadcrumbTrail()}
                ></platform-breadcrumbs>
                <span class="spacer"></span>
                ${this._renderEditedBy()}
                <span>${this._page.is_published ? this.t('page.published') : this.t('page.draft')}</span>
                <platform-switch
                    class="full-width-switch"
                    size="sm"
                    data-wiki-full-width
                    ?checked=${this._page.is_full_width === true}
                    label=${this.t('page.full_width')}
                    @change=${this._onFullWidthChange}
                ></platform-switch>
                <button
                    class="ghost-btn"
                    type="button"
                    data-wiki-panel-comments
                    aria-label=${this.t('page.comments')}
                    title=${this.t('page.comments')}
                    @click=${() => this._togglePanel('comments')}
                >
                    <platform-icon name="chat" size="16"></platform-icon>
                </button>
                <button
                    class="ghost-btn"
                    type="button"
                    data-wiki-panel-toggle
                    aria-label=${this.t('panel.open')}
                    title=${this.t('panel.open')}
                    @click=${() => this._togglePanel('outline')}
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
                    <platform-icon name="more-vert" size="16"></platform-icon>
                </button>
            </div>
        `;
    }

    async _onFullWidthChange(event) {
        const detail = event.detail;
        if (detail === null || typeof detail !== 'object' || typeof detail.value !== 'boolean') {
            throw new Error('wiki-page-view: full width switch change without boolean value');
        }
        const fullWidth = detail.value;
        await this._properties.run({ wiki_page_id: this.pageId, is_full_width: fullWidth });
        this._page = { ...this._page, is_full_width: fullWidth };
    }

    /** Автор последней правки — вход в историю версий: иначе её не видно. */
    _renderEditedBy() {
        return html`
            <button
                class="edited"
                type="button"
                data-wiki-edited-by
                title=${this.t('history.title')}
                @click=${() => this._togglePanel('history')}
            >
                <span>${this.t('page.edited_label')}</span>
                <platform-user-chip user-id=${this._page.last_edited_by_user_id} size="sm"></platform-user-chip>
                <span>${formatPlatformDateTime(new Date(this._page.updated_at), this._locale.value)}</span>
            </button>
        `;
    }

    /**
     * Путь от корня пространства до текущей страницы: маршруты роутера
     * вложенность страниц не выражают, её знает только дерево.
     */
    _breadcrumbTrail() {
        const byId = new Map(this._pages.items.map((page) => [page.wiki_page_id, page]));
        const chain = [];
        let parentId = this._page.parent_page_id;
        while (typeof parentId === 'string' && parentId !== '' && !chain.some((page) => page.wiki_page_id === parentId)) {
            const parent = byId.get(parentId);
            if (parent === undefined) {
                break;
            }
            chain.unshift(parent);
            parentId = parent.parent_page_id;
        }
        return chain.map((page) => ({
            label: page.title === '' ? this.t('page.untitled') : page.title,
            routeKey: 'wiki_page',
            params: { pageId: page.wiki_page_id },
        }));
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
                    ? html`<platform-icon name="smile" size="48"></platform-icon>`
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

    _scrollToHeading(target) {
        if (!target || typeof target !== 'object') {
            throw new Error('wiki-page-view: outline target required');
        }
        const editor = this.renderRoot.querySelector('platform-rich-editor');
        if (!editor) {
            throw new Error('wiki-page-view: rich editor missing');
        }
        // После save/import позиции в панели могут отстать от живого документа —
        // сверяем с актуальным оглавлением редактора.
        const live = editor.getOutline();
        this._outline = live;
        const pos = target.pos;
        const text = typeof target.text === 'string' ? target.text : '';
        const level = target.level;
        const match = live.find((item) => item.pos === pos)
            || live.find((item) => item.text === text && item.level === level)
            || live.find((item) => item.text === text);
        if (!match) {
            throw new Error(
                `wiki-page-view: heading not found in live outline (pos=${String(pos)}, text=${text})`,
            );
        }
        editor.scrollToPosition(match.pos);
    }
}

customElements.define('wiki-page-view', WikiPageView);
