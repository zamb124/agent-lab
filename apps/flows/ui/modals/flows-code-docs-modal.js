/**
 * Документация inline-кода: Markdown с API, слева оглавление и поиск в шапке сайдбара.
 */

import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/common/flows-code-language-icon.js';
import { asObject } from '../_helpers/flows-resolvers.js';
import {
    FLOW_CODE_LANGUAGES,
    flowCodeLanguageLabel,
    normalizeFlowCodeLanguage,
} from '../_helpers/flows-code-languages.js';

function _lower(s) {
    if (typeof s === 'string' && s.length > 0) {
        return s.toLowerCase();
    }
    return '';
}

/**
 * @param {string} md
 * @returns {Array<{ level: number, text: string, id: string | null }>}
 */
function buildTocFromMarkdown(md) {
    if (typeof md !== 'string' || md.length === 0) {
        return [];
    }
    const items = [];
    const lines = md.split('\n');
    let inFence = false;
    const htmlH = /^<h([1-3])[^>]*\sid="([^"]+)"[^>]*>([^<]*)<\/h[1-3]>\s*$/i;
    const mdH = /^(#{2,3})(?!#)\s+(.+)$/;
    for (const line of lines) {
        const tr = line.trim();
        if (tr.startsWith('```')) {
            inFence = !inFence;
            continue;
        }
        if (inFence) {
            continue;
        }
        let m = line.match(htmlH);
        if (m) {
            const text = m[3].replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');
            items.push({ level: Number(m[1]), id: m[2], text: text.trim() });
            continue;
        }
        m = line.match(mdH);
        if (m) {
            const level = m[1].length;
            const text = m[2].replace(/`+/g, '').trim();
            items.push({ level, id: null, text });
        }
    }
    return items;
}

/**
 * @param {unknown} result
 * @returns {string}
 */
function getDocsMarkdown(result) {
    if (typeof result === 'string') {
        return result;
    }
    if (result && typeof result === 'object' && typeof result.markdown === 'string') {
        return result.markdown;
    }
    return JSON.stringify(asObject(result), null, 2);
}

/**
 * @param {string} md
 * @returns {string}
 */
function markdownToHtml(md) {
    const marked = globalThis.marked;
    if (marked && typeof marked.parse === 'function') {
        if (typeof marked.setOptions === 'function') {
            marked.setOptions({ gfm: true, breaks: true, mangle: false, headerIds: true });
        }
        return marked.parse(md);
    }
    return `<pre class="docs-md-fallback">${md.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`;
}

export class FlowsCodeDocsModal extends PlatformModal {
    static modalKind = 'flows.code_docs';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        language: { type: String },
        documentationPerspective: { type: String },
        _search: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .docs-layout {
                display: flex;
                flex-direction: row;
                align-items: stretch;
                gap: 0;
                min-height: min(70vh, 720px);
                max-height: min(80vh, 900px);
            }
            .docs-sidebar {
                width: 280px;
                flex-shrink: 0;
                display: flex;
                flex-direction: column;
                border-right: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md) 0 0 var(--radius-md);
                min-height: 0;
            }
            .docs-sidebar-top {
                display: flex;
                flex-direction: column;
                justify-content: flex-start;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }
            .docs-sidebar-search {
                width: 100%;
                min-width: 0;
            }
            .language-segment {
                display: grid;
                grid-template-columns: repeat(5, minmax(0, 1fr));
                width: 100%;
                gap: 2px;
                padding: 2px;
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                box-sizing: border-box;
            }
            .language-button {
                width: 36px;
                height: 28px;
                padding: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border: 0;
                border-radius: calc(var(--radius-md) - 2px);
                background: transparent;
                color: var(--text-tertiary);
                font-size: 11px;
                font-weight: var(--font-semibold);
                cursor: pointer;
            }
            .language-button:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            .language-button[active] {
                color: var(--accent);
                background: var(--accent-subtle);
            }
            .language-button:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }
            .language-button flows-code-language-icon {
                pointer-events: none;
            }
            .docs-toc {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-2) 0;
            }
            .docs-toc-link {
                display: block;
                width: 100%;
                text-align: left;
                padding: 6px var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: none;
                border: none;
                cursor: pointer;
                border-left: 2px solid transparent;
                line-height: 1.3;
            }
            .docs-toc-link:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            .docs-toc-link--nested {
                padding-left: calc(var(--space-3) + var(--space-4));
                font-size: var(--text-xs);
                font-weight: var(--font-regular);
            }
            .docs-toc-empty {
                padding: var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .docs-main {
                flex: 1;
                min-width: 0;
                overflow: auto;
                padding: var(--space-3) var(--space-4);
            }
            .docs-md {
                font-size: var(--text-sm);
                line-height: 1.55;
                color: var(--text-primary);
                max-width: 900px;
            }
            .docs-md h1,
            .docs-md h2,
            .docs-md h3,
            .docs-md h4 {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                margin: var(--space-4) 0 var(--space-2) 0;
                scroll-margin-top: var(--space-3);
            }
            .docs-md h1 {
                font-size: var(--text-xl);
            }
            .docs-md h2 {
                font-size: var(--text-lg);
            }
            .docs-md h3 {
                font-size: var(--text-md);
            }
            .docs-md p {
                margin: 0 0 var(--space-3) 0;
            }
            .docs-md a {
                color: var(--accent);
                text-decoration: none;
            }
            .docs-md a:hover {
                text-decoration: underline;
            }
            .docs-md code {
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: 0.9em;
                background: var(--glass-tint-medium);
                padding: 0.1em 0.35em;
                border-radius: var(--radius-sm);
            }
            .docs-md pre {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                overflow: auto;
                font-size: var(--text-xs);
            }
            .docs-md pre code {
                background: none;
                padding: 0;
            }
            .docs-md table {
                border-collapse: collapse;
                width: 100%;
                font-size: var(--text-xs);
                margin: var(--space-3) 0;
            }
            .docs-md th,
            .docs-md td {
                border: 1px solid var(--glass-border-subtle);
                padding: var(--space-2);
                text-align: left;
            }
            .docs-md th {
                background: var(--glass-solid-subtle);
            }
            .docs-md ul,
            .docs-md ol {
                margin: 0 0 var(--space-3) 0;
                padding-left: 1.25em;
            }
            .docs-md li {
                margin: 0.25em 0;
            }
            .docs-md blockquote {
                border-left: 3px solid var(--accent);
                margin: var(--space-3) 0;
                padding-left: var(--space-3);
                color: var(--text-secondary);
            }
            .docs-md-fallback {
                white-space: pre-wrap;
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.language = 'python';
        this.documentationPerspective = 'editor';
        this._search = '';
        this._docsOp = this.useOp('flows/code_documentation');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('open') && this.open) {
            this._search = '';
            void this._loadDocumentation();
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (this.open && (changed.has('language') || changed.has('documentationPerspective'))) {
            void this._loadDocumentation();
        }
    }

    _documentationLanguage() {
        return normalizeFlowCodeLanguage(this.language);
    }

    _documentationPerspective() {
        return typeof this.documentationPerspective === 'string' && this.documentationPerspective.length > 0
            ? this.documentationPerspective
            : 'editor';
    }

    async _loadDocumentation() {
        await this._docsOp.run({
            language: this._documentationLanguage(),
            perspective: this._documentationPerspective(),
        });
    }

    _onSearchInput(e) {
        this._search = typeof e.detail?.value === 'string' ? e.detail.value : '';
    }

    _scrollToTarget(item) {
        const main = this.renderRoot?.querySelector('.docs-main .docs-md');
        if (!main) {
            return;
        }
        if (item.id) {
            const el = main.querySelector(`#${CSS.escape(item.id)}`);
            if (el) {
                el.scrollIntoView({ block: 'start', behavior: 'smooth' });
            }
            return;
        }
        const want = item.text;
        if (typeof want !== 'string' || want.length === 0) {
            return;
        }
        const hs = main.querySelectorAll('h2, h3');
        for (const h of hs) {
            if (h.textContent && h.textContent.trim() === want) {
                h.scrollIntoView({ block: 'start', behavior: 'smooth' });
                return;
            }
        }
    }

    _filteredToc(toc) {
        const q = _lower(this._search);
        if (q.length === 0) {
            return toc;
        }
        return toc.filter((it) => _lower(it.text).indexOf(q) >= 0);
    }

    _setLanguage(language) {
        this.language = normalizeFlowCodeLanguage(language);
    }

    _renderLanguageSegment() {
        const current = this._documentationLanguage();
        return html`
            <div class="language-segment" role="group" aria-label=${this.t('code_workbench.language_aria')}>
                ${FLOW_CODE_LANGUAGES.map((lang) => html`
                    <button
                        type="button"
                        class="language-button"
                        ?active=${current === lang.value}
                        title=${lang.label}
                        aria-label=${lang.label}
                        @click=${() => this._setLanguage(lang.value)}
                    >
                        <flows-code-language-icon language=${lang.value} size="18"></flows-code-language-icon>
                    </button>
                `)}
            </div>
        `;
    }

    renderHeader() {
        return `${this.t('code_docs_modal.title')} · ${flowCodeLanguageLabel(this._documentationLanguage())}`;
    }

    renderBody() {
        const result = this._docsOp.lastResult;
        if (this._docsOp.busy) {
            return html`<glass-spinner></glass-spinner>`;
        }
        const md = getDocsMarkdown(result);
        const htmlStr = markdownToHtml(md);
        const toc = buildTocFromMarkdown(md);
        const shown = this._filteredToc(toc);
        return html`
            <div class="docs-layout">
                <aside class="docs-sidebar" aria-label=${this.t('code_docs_modal.toc_aria')}>
                    <div class="docs-sidebar-top">
                        ${this._renderLanguageSegment()}
                        <div class="docs-sidebar-search">
                            <platform-field
                                type="string"
                                input-type="search"
                                mode="edit"
                                .value=${this._search}
                                .placeholder=${this.t('code_docs_modal.search_placeholder')}
                                @change=${this._onSearchInput}
                            ></platform-field>
                        </div>
                    </div>
                    <nav class="docs-toc">
                        ${shown.length === 0
                            ? html`<div class="docs-toc-empty">${this.t('code_docs_modal.toc_empty')}</div>`
                            : shown.map(
                                (it) => html`
                                <button
                                    type="button"
                                    class="docs-toc-link ${it.level >= 3 ? 'docs-toc-link--nested' : ''}"
                                    @click=${() => this._scrollToTarget(it)}
                                >${it.text}</button>
                            `,
                            )}
                    </nav>
                </aside>
                <div class="docs-main">
                    <div class="docs-md">${unsafeHTML(htmlStr)}</div>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-code-docs-modal', FlowsCodeDocsModal);
registerModalKind(FlowsCodeDocsModal.modalKind, 'flows-code-docs-modal');
