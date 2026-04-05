/**
 * CodeDocsModal — документация inline-кода (Markdown с сервера).
 * Якоря #id внутри Shadow DOM: клики перехватываются, скролл через scrollIntoView.
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

function _escapeAttr(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;');
}

/**
 * В тексте документации не должно быть реальных img с внешними URL (примерные ссылки дают запросы в Network).
 */
function neutralizeDocumentationImages(html) {
    if (!html || typeof html !== 'string') {
        return html;
    }
    return html.replace(/<img\b[^>]*>/gi, (tag) => {
        const altM = /\balt\s*=\s*["']([^"']*)["']/i.exec(tag);
        const srcM = /\bsrc\s*=\s*["']([^"']*)["']/i.exec(tag);
        const alt = (altM ? altM[1] : '').trim();
        const label = alt || 'изображение';
        const hint = srcM ? srcM[1] : '';
        const title = hint ? ` title="${_escapeAttr(hint)}"` : '';
        return `<span class="docs-md-img-stub"${title}>${_escapeAttr(label)}</span>`;
    });
}

const FIND_MARK_CLASS = 'docs-in-page-find';

function _escapeRegExp(s) {
    return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function _unwrapFindMarks(root) {
    if (!root) {
        return;
    }
    const marks = [...root.querySelectorAll(`mark.${FIND_MARK_CLASS}`)];
    for (const mark of marks) {
        const parent = mark.parentNode;
        if (!parent) {
            continue;
        }
        while (mark.firstChild) {
            parent.insertBefore(mark.firstChild, mark);
        }
        parent.removeChild(mark);
    }
    root.normalize();
}

function _collectTextNodesForFind(root) {
    const out = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            const t = node.nodeValue;
            if (!t || t.length === 0) {
                return NodeFilter.FILTER_REJECT;
            }
            const el = node.parentElement;
            if (!el) {
                return NodeFilter.FILTER_REJECT;
            }
            if (el.closest(`mark.${FIND_MARK_CLASS}`)) {
                return NodeFilter.FILTER_REJECT;
            }
            const tag = el.tagName;
            if (tag === 'SCRIPT' || tag === 'STYLE') {
                return NodeFilter.FILTER_REJECT;
            }
            return NodeFilter.FILTER_ACCEPT;
        },
    });
    let cur;
    while ((cur = walker.nextNode())) {
        out.push(cur);
    }
    return out;
}

function _wrapMatchesInTextNode(textNode, needle) {
    const re = new RegExp(_escapeRegExp(needle), 'gi');
    const text = textNode.nodeValue;
    const matches = [...text.matchAll(re)];
    if (matches.length === 0) {
        return;
    }
    const parent = textNode.parentNode;
    if (!parent) {
        return;
    }
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of matches) {
        const idx = m.index;
        const chunk = m[0];
        if (idx > last) {
            frag.appendChild(document.createTextNode(text.slice(last, idx)));
        }
        const mark = document.createElement('mark');
        mark.className = FIND_MARK_CLASS;
        mark.appendChild(document.createTextNode(chunk));
        frag.appendChild(mark);
        last = idx + chunk.length;
    }
    if (last < text.length) {
        frag.appendChild(document.createTextNode(text.slice(last)));
    }
    parent.replaceChild(frag, textNode);
}

const DOC_SECTION_IDS = [
    { id: 'doc-globals', i18nKey: 'code_docs.nav_globals' },
    { id: 'doc-modules', i18nKey: 'code_docs.nav_modules' },
    { id: 'doc-state', i18nKey: 'code_docs.nav_state' },
    { id: 'doc-builtins', i18nKey: 'code_docs.nav_builtins' },
    { id: 'doc-platform-tools', i18nKey: 'code_docs.nav_platform_tools' },
    { id: 'doc-templates', i18nKey: 'code_docs.nav_templates' },
];

export class CodeDocsModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 960px;
            }

            :host .modal-header {
                flex-wrap: nowrap;
                align-items: center;
                column-gap: var(--space-2);
            }

            :host .header-buttons {
                min-width: 0;
                flex-shrink: 1;
            }

            :host .modal-title {
                display: flex;
                align-items: center;
                min-width: 0;
                flex: 1 1 auto;
                max-width: 42%;
            }

            .code-docs-title-row {
                display: inline-flex;
                align-items: center;
                gap: var(--space-3);
                min-width: 0;
            }

            .code-docs-title-row .modal-icon {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                margin: 0;
                border-radius: var(--radius-full);
                flex-shrink: 0;
                font-size: var(--text-lg);
                background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                color: white;
                box-shadow:
                    0 4px 16px rgba(59, 130, 246, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }

            .code-docs-title-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                line-height: 1.3;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .code-docs-header-actions {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
                flex: 0 1 auto;
                min-width: 0;
                max-width: 100%;
            }

            .code-docs-nav-tags {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                gap: 4px;
                align-items: center;
                justify-content: flex-end;
                min-width: 0;
                max-width: min(340px, 50vw);
                overflow-x: auto;
                overflow-y: hidden;
                flex-shrink: 1;
                scrollbar-width: thin;
                -webkit-overflow-scrolling: touch;
            }

            .code-docs-nav-tag {
                padding: 2px 8px;
                font-size: 11px;
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-full);
                cursor: pointer;
                transition:
                    color var(--duration-fast) var(--easing-default),
                    background var(--duration-fast) var(--easing-default),
                    border-color var(--duration-fast) var(--easing-default);
                white-space: nowrap;
            }

            .code-docs-nav-tag:hover {
                color: var(--accent);
                background: var(--accent-bg);
                border-color: var(--accent);
            }

            .code-docs-search-field {
                flex: 0 0 auto;
                width: 148px;
                min-width: 96px;
                max-width: 180px;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                outline: none;
                backdrop-filter: blur(var(--glass-blur-subtle));
                -webkit-backdrop-filter: blur(var(--glass-blur-subtle));
            }

            .code-docs-search-field:focus {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }

            .docs-md-img-stub {
                display: inline;
                padding: 1px 6px;
                font-size: 0.92em;
                font-style: italic;
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-sm);
            }

            .docs-markdown mark.docs-in-page-find {
                padding: 0 2px;
                margin: 0 -2px;
                border-radius: 2px;
                background: color-mix(in srgb, #fbbf24 55%, transparent);
                color: inherit;
                box-shadow: 0 0 0 1px color-mix(in srgb, #f59e0b 40%, transparent);
            }

            .docs-markdown mark.docs-in-page-find.docs-in-page-find-active {
                background: color-mix(in srgb, #f59e0b 70%, transparent);
                box-shadow: 0 0 0 2px var(--accent);
            }

            .docs-content {
                padding: var(--space-4);
                max-height: 65vh;
                overflow-y: auto;
            }

            .docs-markdown {
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1.55;
                overflow-wrap: anywhere;
                word-break: break-word;
                max-width: 100%;
            }

            .docs-markdown > :first-child {
                margin-top: 0;
            }

            .docs-markdown > :last-child {
                margin-bottom: 0;
            }

            .docs-markdown p,
            .docs-markdown ul,
            .docs-markdown ol,
            .docs-markdown blockquote,
            .docs-markdown pre,
            .docs-markdown h1,
            .docs-markdown h2,
            .docs-markdown h3,
            .docs-markdown h4 {
                margin: 0 0 var(--space-3) 0;
            }

            .docs-markdown h1 {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                border-bottom: 1px solid var(--border-subtle);
                padding-bottom: var(--space-2);
            }

            .docs-markdown h2 {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                margin-top: var(--space-4);
                scroll-margin-top: var(--space-3);
            }

            .docs-markdown h3 {
                font-size: var(--text-base);
                font-weight: var(--font-medium);
                margin-top: var(--space-3);
                scroll-margin-top: var(--space-3);
            }

            .docs-markdown h3.docs-platform-tool-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--accent);
                margin-top: var(--space-4);
                scroll-margin-top: var(--space-3);
            }

            .docs-markdown ul,
            .docs-markdown ol {
                padding-left: 1.25rem;
            }

            .docs-markdown code {
                font-family: var(--font-mono);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-sm);
                padding: 1px 6px;
                font-size: 0.92em;
            }

            .docs-markdown pre {
                background: var(--glass-tint-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                overflow: auto;
            }

            .docs-markdown pre code {
                background: transparent;
                border-radius: 0;
                padding: 0;
                font-size: var(--text-xs);
            }

            .docs-markdown table {
                width: 100%;
                border-collapse: collapse;
                font-size: var(--text-xs);
                margin-bottom: var(--space-3);
            }

            .docs-markdown th,
            .docs-markdown td {
                border: 1px solid var(--border-subtle);
                padding: var(--space-2) var(--space-2);
                text-align: left;
                vertical-align: top;
            }

            .docs-markdown th {
                background: var(--glass-tint-subtle);
                font-weight: var(--font-medium);
            }

            .docs-markdown a {
                color: var(--accent);
                text-decoration: none;
            }

            .docs-markdown a:hover {
                text-decoration: underline;
            }

            .docs-raw {
                margin: 0;
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                white-space: pre-wrap;
                word-break: break-word;
            }

            .loading {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-8);
                color: var(--text-tertiary);
            }

            .empty-state {
                text-align: center;
                padding: var(--space-6);
                color: var(--text-tertiary);
            }
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        language: { type: String },
        nodeType: { type: String },
        perspective: { type: String },
        _markdown: { type: String, state: true },
        _loading: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this.size = 'lg';
        this.language = 'python';
        this.nodeType = 'code';
        this.perspective = 'editor';
        this._markdown = '';
        this._loading = false;
        this._findActiveIndex = 0;
    }

    async showModal(options = {}) {
        this.language = options.language || 'python';
        this.nodeType = options.nodeType || 'code';
        this.perspective = options.perspective || 'editor';
        super.showModal();
        await this._loadDocs();
    }

    async _loadDocs() {
        this._loading = true;
        this._markdown = '';
        try {
            const text = await this.a2a.get('/api/v1/code/documentation', {
                language: this.language,
                perspective: this.perspective,
            });
            if (typeof text === 'string' && text.trim().length > 0) {
                this._markdown = text;
            }
        } catch (e) {
            console.error('Failed to load docs:', e);
        } finally {
            this._loading = false;
        }
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('_markdown') && this._markdown) {
            const input = this._docsModalRoot()?.querySelector('input.code-docs-search-field');
            if (input) {
                input.value = '';
            }
            this._findActiveIndex = 0;
            this._clearInPageFind();
        }
        void this.updateComplete.then(() => {
            const value = this._getSearchInputValue().trim();
            if (value) {
                this._applyInPageFind(value);
            }
        });
    }

    _getLanguageLabel() {
        return this.language === 'javascript' ? 'JavaScript' : 'Python';
    }

    renderHeader() {
        return html`
            <span class="code-docs-title-row">
                <span class="modal-icon info" aria-hidden="true">
                    <platform-icon name="book-open" size="20"></platform-icon>
                </span>
                <span class="code-docs-title-text">
                    ${this.i18n.t('code_docs.header', { language: this._getLanguageLabel() })}
                </span>
            </span>
        `;
    }

    renderHeaderActions() {
        return html`
            <div class="code-docs-header-actions">
                <div class="code-docs-nav-tags" role="navigation" aria-label=${this.i18n.t('code_docs.nav_aria')}>
                    ${DOC_SECTION_IDS.map(
                        (s) => html`
                            <button
                                type="button"
                                class="code-docs-nav-tag"
                                @click=${() => this._scrollToAnchor(s.id)}
                            >
                                ${this.i18n.t(s.i18nKey)}
                            </button>
                        `
                    )}
                </div>
                <input
                    type="text"
                    class="code-docs-search-field"
                    autocomplete="off"
                    spellcheck="false"
                    aria-label=${this.i18n.t('code_docs.search_placeholder')}
                    placeholder=${this.i18n.t('code_docs.search_placeholder')}
                    @input=${(e) => this._onNativeSearchInput(e)}
                    @keydown=${(e) => this._onNativeSearchKeydown(e)}
                />
            </div>
        `;
    }

    _docsModalRoot() {
        return this.shadowRoot ?? this.renderRoot ?? null;
    }

    _getSearchInputValue() {
        const el = this._docsModalRoot()?.querySelector('input.code-docs-search-field');
        if (el && typeof el.value === 'string') {
            return el.value;
        }
        return '';
    }

    _onNativeSearchInput(e) {
        const t = e.target;
        const value = t && typeof t.value === 'string' ? t.value : '';
        this._applyInPageFind(value);
    }

    _onNativeSearchKeydown(e) {
        if (e.key !== 'Enter') {
            return;
        }
        e.preventDefault();
        const root = this._docsModalRoot()?.querySelector('.docs-markdown');
        if (!root) {
            return;
        }
        const marks = [...root.querySelectorAll(`mark.${FIND_MARK_CLASS}`)];
        if (marks.length === 0) {
            const value = e.target && typeof e.target.value === 'string' ? e.target.value : '';
            this._applyInPageFind(value);
            return;
        }
        this._findActiveIndex = (this._findActiveIndex + 1) % marks.length;
        this._syncFindActiveHighlight(root);
    }

    _clearInPageFind() {
        const root = this._docsModalRoot()?.querySelector('.docs-markdown');
        if (!root) {
            return;
        }
        _unwrapFindMarks(root);
        this._findActiveIndex = 0;
    }

    _syncFindActiveHighlight(root) {
        const marks = [...root.querySelectorAll(`mark.${FIND_MARK_CLASS}`)];
        for (const m of marks) {
            m.classList.remove('docs-in-page-find-active');
        }
        if (marks.length === 0) {
            return;
        }
        const i = Math.min(Math.max(this._findActiveIndex, 0), marks.length - 1);
        const el = marks[i];
        el.classList.add('docs-in-page-find-active');
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    _applyInPageFind(rawQuery) {
        const root = this._docsModalRoot()?.querySelector('.docs-markdown');
        if (!root) {
            return;
        }
        const q = rawQuery.trim();
        _unwrapFindMarks(root);
        this._findActiveIndex = 0;
        if (!q) {
            return;
        }
        const qLower = q.toLowerCase();
        const nodes = _collectTextNodesForFind(root);
        for (let i = nodes.length - 1; i >= 0; i--) {
            const tn = nodes[i];
            if (!tn.parentNode || tn.nodeType !== Node.TEXT_NODE) {
                continue;
            }
            const nv = tn.nodeValue;
            if (!nv || !nv.toLowerCase().includes(qLower)) {
                continue;
            }
            _wrapMatchesInTextNode(tn, q);
        }
        this._syncFindActiveHighlight(root);
    }

    _scrollToAnchor(id) {
        if (!id) {
            return;
        }
        let target = this.shadowRoot?.getElementById(id);
        if (!target && this.shadowRoot) {
            try {
                target = this.shadowRoot.querySelector(`[id="${CSS.escape(id)}"]`);
            } catch {
                target = null;
            }
        }
        target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    _onDocsContentClick(e) {
        const raw = e.target;
        const el =
            raw instanceof Element
                ? raw
                : raw?.parentElement instanceof Element
                  ? raw.parentElement
                  : null;
        if (!el) {
            return;
        }
        const a = el.closest('a[href]');
        if (!a || !this.shadowRoot?.contains(a)) {
            return;
        }
        const href = a.getAttribute('href');
        if (!href || href.startsWith('http') || href.startsWith('//')) {
            return;
        }
        if (!href.startsWith('#')) {
            return;
        }
        const id = decodeURIComponent(href.slice(1));
        if (!id) {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        this._scrollToAnchor(id);
    }

    renderBody() {
        if (this._loading) {
            return html`<div class="loading">${this.i18n.t('code_docs.loading')}</div>`;
        }

        if (!this._markdown) {
            return html`<div class="empty-state">${this.i18n.t('code_docs.load_failed')}</div>`;
        }

        if (window.marked && typeof window.marked.parse === 'function') {
            const parsed = window.marked.parse(this._markdown, {
                gfm: true,
                breaks: true,
            });
            const htmlContent = neutralizeDocumentationImages(parsed);
            return html`
                <div class="docs-content" @click=${(e) => this._onDocsContentClick(e)}>
                    <div class="docs-markdown">${unsafeHTML(htmlContent)}</div>
                </div>
            `;
        }

        return html`
            <div class="docs-content">
                <div class="docs-markdown">
                    <pre class="docs-raw">${this._markdown}</pre>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return null;
    }
}

customElements.define('code-docs-modal', CodeDocsModal);
