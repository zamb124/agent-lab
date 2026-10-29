/**
 * Публичный сайт: страница по анонимной ссылке, только чтение и без сессии.
 *
 * Ссылка живёт на корне раздела, а сайт — его опубликованное поддерево, поэтому
 * страница сразу отдаёт навигацию: слева дерево, сверху путь. Подстраница
 * открывается по тому же токену.
 *
 * Заголовок документа берётся из страницы — по ссылке делятся в мессенджерах, и
 * подпись вкладки единственное, что видно до открытия. OG-разметки здесь нет
 * намеренно: ссылка секретная, wiki отдаётся под `noindex`, а без SSR краулер
 * всё равно увидит пустой каркас.
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues } from '@platform/lib/lit-shim.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

interface WikiPublicPage {
    title?: unknown;
    icon?: unknown;
    cover_url?: unknown;
    is_full_width?: unknown;
    content?: unknown;
    parent_page_id?: unknown;
    [key: string]: unknown;
}

interface WikiPublicTreeItem {
    wiki_page_id?: string;
    parent_page_id?: unknown;
    title?: unknown;
    icon?: unknown;
    has_children?: unknown;
    [key: string]: unknown;
}

interface WikiPublicTree {
    items?: WikiPublicTreeItem[];
    root_page_id?: string;
    [key: string]: unknown;
}
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-rich-editor.js';
import '@platform/lib/components/platform-tree.js';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function publicPage(value: unknown): WikiPublicPage {
    if (!isPlainRecord(value)) {
        throw new Error('wiki public read: page response is empty');
    }
    const page: WikiPublicPage = {};
    for (const [key, field] of Object.entries(value)) page[key] = field;
    return page;
}

function treeItem(value: unknown): WikiPublicTreeItem {
    if (!isPlainRecord(value)) {
        throw new Error('wiki public read: tree item must be an object');
    }
    const item: WikiPublicTreeItem = {};
    for (const [key, field] of Object.entries(value)) {
        if (key === 'wiki_page_id') {
            if (field !== undefined && typeof field !== 'string') {
                throw new Error('wiki public read: tree item wiki_page_id must be a string');
            }
            if (typeof field === 'string') item.wiki_page_id = field;
            continue;
        }
        item[key] = field;
    }
    return item;
}

function publicTree(value: unknown): WikiPublicTree {
    if (!isPlainRecord(value)) {
        throw new Error('wiki public read: tree response is empty');
    }
    const tree: WikiPublicTree = {};
    if (value.root_page_id !== undefined) {
        if (typeof value.root_page_id !== 'string') {
            throw new Error('wiki public read: root_page_id must be a string');
        }
        tree.root_page_id = value.root_page_id;
    }
    if (value.items != null) {
        if (!Array.isArray(value.items)) {
            throw new Error('wiki public read: tree items must be an array');
        }
        tree.items = value.items.map(treeItem);
    }
    for (const [key, field] of Object.entries(value)) {
        if (key === 'items' || key === 'root_page_id') continue;
        tree[key] = field;
    }
    return tree;
}


export class WikiPublicPreviewPage extends PlatformPage {
    static i18nNamespace = 'wiki';

    declare token: string;
    declare pageId: string;
    declare _page: WikiPublicPage | null;
    declare _tree: WikiPublicTree | null;
    declare _failed: boolean;
    private _publicPage: OpController;
    private _publicSitePage: OpController;
    private _publicTree: OpController;

    static override properties = {
        token: { type: String },
        /** Пусто на корне сайта: там страницу отдаёт сам токен. */
        pageId: { type: String, attribute: 'page-id' },
        _page: { state: true },
        _tree: { state: true },
        _failed: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                height: 100%;
                min-height: 0;
            }

            .site {
                display: flex;
                height: 100%;
                min-height: 0;
            }

            .nav {
                flex: 0 0 var(--wiki-outline-width);
                min-width: 0;
                padding: var(--space-4) var(--space-2);
                border-right: 1px solid var(--glass-border-subtle);
                overflow-y: auto;
                box-sizing: border-box;
            }

            .scroll {
                flex: 1;
                min-width: 0;
                overflow-y: auto;
            }

            /* Путь идёт по всей ширине области чтения и липнет к верху — как в
               приложении, чтобы с длинной страницы можно было выйти наверх. */
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

            .spacer {
                flex: 1;
            }

            .nav-btn {
                display: none;
                align-items: center;
                justify-content: center;
                padding: 3px var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
            }

            .cover {
                height: var(--wiki-cover-height);
                background-size: cover;
                background-position: center;
            }

            .paper {
                max-width: var(--wiki-page-max-width);
                margin: 0 auto;
                padding: var(--space-4) var(--wiki-block-gutter) var(--space-10);
            }

            .paper[data-full-width] {
                max-width: none;
            }

            .title-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin: var(--space-2) 0 var(--space-6);
                min-width: 0;
            }

            .icon {
                flex-shrink: 0;
                font-size: 80px;
                line-height: 1;
            }

            .title {
                margin: 0;
                min-width: 0;
                font-size: 48px;
                font-weight: var(--font-bold);
                line-height: 1.12;
                letter-spacing: -0.03em;
                color: var(--text-primary);
            }

            .state {
                padding: var(--space-10);
                text-align: center;
                color: var(--text-tertiary);
            }

            .state-hint {
                margin-top: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-disabled);
            }

            /* Узкий экран: дерево уходит в bottom-sheet по кнопке в шапке —
               нижней навигации на публичном сайте нет. */
            @media (max-width: 767px) {
                .nav {
                    display: none;
                }
                .nav-btn {
                    display: inline-flex;
                }
                .paper {
                    padding: var(--space-3) var(--space-4) var(--space-10);
                }
                .title {
                    font-size: 32px;
                }
                .icon {
                    font-size: 56px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.token = '';
        this.pageId = '';
        this._page = null;
        this._tree = null;
        this._failed = false;
        this._publicPage = this.useOp('wiki/public_page');
        this._publicSitePage = this.useOp('wiki/public_site_page');
        this._publicTree = this.useOp('wiki/public_tree');

    }

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        if ((changed.has('token') || changed.has('pageId')) && this.token !== '') {
            void this._load();
        }
    }

    /** 404 публичного чтения — отключённая ссылка, черновик или страница вне раздела. */
    private _publicReadMissed(op: OpController): boolean {
        if (op.error === null) {
            return false;
        }
        if (op.failureStatus === 404) {
            this._failed = true;
            this._tree = null;
            return true;
        }
        throw new Error(`wiki public read failed: ${op.error}`);
    }

    private async _load(): Promise<void> {
        this._failed = false;
        this._page = null;
        const pageOp = this.pageId === '' ? this._publicPage : this._publicSitePage;
        const page = this.pageId === ''
            ? await this._publicPage.run({ link_token: this.token })
            : await this._publicSitePage.run({
                link_token: this.token,
                wiki_page_id: this.pageId,
            });
        if (this._publicReadMissed(pageOp)) {
            document.title = this.t('public.not_found');
            return;
        }
        this._page = publicPage(page);
        const tree = await this._publicTree.run({ link_token: this.token });
        if (this._publicReadMissed(this._publicTree)) {
            document.title = this.t('public.not_found');
            return;
        }
        this._tree = publicTree(tree);
        document.title = this._pageTitle();
    }

    private _pageTitle() {
        if (this._page === null || this._page.title === '') {
            return this.t('page.untitled');
        }
        return missingAsEmpty(this._page.title);
    }

    private _treeItems(): WikiPublicTreeItem[] {
        if (this._tree === null || !Array.isArray(this._tree.items)) {
            return [];
        }
        return this._tree.items;
    }

    private _treeNodes(): Record<string, unknown>[] {
        return this._treeItems().map((item: WikiPublicTreeItem) => ({
            id: item.wiki_page_id,
            parent_id: item.parent_page_id,
            label: item.title === '' ? this.t('page.untitled') : item.title,
            emoji: item.icon === '' ? undefined : item.icon,
            icon: 'file',
            has_children: item.has_children,
        }));
    }

    /** Корень открывается коротким адресом ссылки, потомки — вложенным. */
    private _openPage(wikiPageId: string) {
        if (this._tree !== null && wikiPageId === this._tree.root_page_id) {
            this.navigate('wiki_public_preview', { token: this.token });
            return;
        }
        this.navigate('wiki_public_page', { token: this.token, pageId: wikiPageId });
    }

    private _onTreeSelect(event: CustomEvent<{ id?: unknown }>) {
        this._openPage(missingAsEmpty(event.detail.id));
    }

    private _openTreeSheet() {
        this.openBottomSheet('wiki.public_tree', {
            nodes: this._treeNodes(),
            selectedId: this._selectedId(),
            onSelect: (wikiPageId: string) => this._openPage(wikiPageId),
        });
    }

    private _selectedId() {
        if (this.pageId !== '') {
            return this.pageId;
        }
        return this._tree === null ? '' : missingAsEmpty(this._tree.root_page_id);
    }

    private _breadcrumbTrail() {
        const byId = new Map(this._treeItems().map((item) => [item.wiki_page_id, item]));
        const chain: WikiPublicTreeItem[] = [];
        let parentId = this._page ? this._page.parent_page_id : null;
        while (
            typeof parentId === 'string'
            && parentId !== ''
            && byId.has(parentId)
            && !chain.some((item) => item.wiki_page_id === parentId)
        ) {
            const parent = byId.get(parentId);
            if (!parent) break;
            chain.unshift(parent);
            parentId = parent.parent_page_id;
        }
        const rootPageId = this._tree === null ? '' : this._tree.root_page_id;
        return chain.map((item: WikiPublicTreeItem) => ({
            label: item.title === '' ? this.t('page.untitled') : item.title,
            routeKey: item.wiki_page_id === rootPageId ? 'wiki_public_preview' : 'wiki_public_page',
            params: item.wiki_page_id === rootPageId
                ? { token: this.token }
                : { token: this.token, pageId: missingAsEmpty(item.wiki_page_id) },
        }));
    }

    override render() {
        if (this._failed) {
            return html`<div class="state">
                ${this.t('public.not_found')}
                <div class="state-hint">${this.t('public.not_found_hint')}</div>
            </div>`;
        }
        if (this._page === null) {
            return html`<div class="state"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        return html`
            <div class="site">
                <div class="nav">
                    <platform-tree
                        .nodes=${this._treeNodes()}
                        selected-id=${this._selectedId()}
                        aria-label=${this.t('public.site_nav')}
                        @tree-select=${(event: CustomEvent<{ id?: unknown }>) => this._onTreeSelect(event)}
                    ></platform-tree>
                </div>
                <div class="scroll">
                    <div class="topbar">
                        <platform-breadcrumbs
                            current-label=${this._pageTitle()}
                            .trail=${this._breadcrumbTrail()}
                        ></platform-breadcrumbs>
                        <span class="spacer"></span>
                        <button
                            class="nav-btn"
                            type="button"
                            data-wiki-public-nav
                            aria-label=${this.t('public.site_nav')}
                            title=${this.t('public.site_nav')}
                            @click=${() => this._openTreeSheet()}
                        >
                            <platform-icon name="trace-tree" size="16"></platform-icon>
                        </button>
                    </div>
                    ${this._page.cover_url === ''
                        ? nothing
                        : html`<div
                            class="cover"
                            style=${`background-image:url(${this._page.cover_url})`}
                        ></div>`}
                    <div class="paper" ?data-full-width=${this._page.is_full_width}>
                        <div class="title-row">
                            ${this._page.icon === '' ? nothing : html`<div class="icon">${this._page.icon}</div>`}
                            <h1 class="title">${this._pageTitle()}</h1>
                        </div>
                        <platform-rich-editor
                            readonly
                            .value=${this._page.content}
                            file-url-base=${`/wiki/api/v1/public/pages/${this.token}/files/`}
                        ></platform-rich-editor>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('wiki-public-preview-page', WikiPublicPreviewPage);
