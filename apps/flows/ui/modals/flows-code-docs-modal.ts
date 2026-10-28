/**
 * Документация inline-кода: Markdown с API, слева оглавление и поиск в шапке сайдбара.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '../components/common/flows-code-language-segment.js';
import { markdownToHtml } from '@platform/lib/utils/markdown.js';
import {
    flowCodeLanguageLabel,
    normalizeFlowCodeLanguage,
} from '../_helpers/flows-code-languages.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

function _lower(s: any) {
    if (typeof s === 'string' && s.length > 0) {
        return s.toLowerCase();
    }
    return '';
}

/**
 * Оглавление по ATX-заголовкам второго и третьего уровня вне code fence.
 *
 * @param {string} md
 * @returns {Array<{ level: number, text: string }>}
 */
function buildTocFromMarkdown(md: any) {
    if (typeof md !== 'string' || md.length === 0) {
        return [];
    }
    const items = [];
    let inFence = false;
    const mdH = /^(#{2,3})(?!#)\s+(.+)$/;
    for (const line of md.split('\n')) {
        if (line.trim().startsWith('```')) {
            inFence = !inFence;
            continue;
        }
        if (inFence) {
            continue;
        }
        const m = line.match(mdH);
        if (m) {
            const marks = m[1];
            const heading = m[2];
            if (marks === undefined || heading === undefined) {
                throw new Error('flows-code-docs-modal: heading match incomplete');
            }
            items.push({ level: marks.length, text: heading.replace(/`+/g, '').trim() });
        }
    }
    return items;
}

/**
 * @param {unknown} result
 * @returns {string}
 */
function getDocsMarkdown(result: any) {
    if (!result || typeof result !== 'object' || typeof result.markdown !== 'string') {
        throw new Error('flows.code_docs: markdown required');
    }
    return result.markdown;
}

export class FlowsCodeDocsModal extends PlatformModal {
    static modalKind = 'flows.code_docs';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        language: { type: String },
        documentationPerspective: { type: String },
        _search: { state: true },
    }
    declare language: string;
    declare documentationPerspective: string;
    declare _search: string;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        panelShellStyles,
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
                min-height: 0;
                border-radius: var(--radius-md) 0 0 var(--radius-md);
            }
            .docs-sidebar-top {
                display: flex;
                flex-direction: column;
                justify-content: flex-start;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                flex-shrink: 0;
            }
            .docs-sidebar-top platform-segmented-control {
                width: 100%;
            }
            .docs-toc {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-2) 0;
            }
            .docs-toc platform-button {
                width: 100%;
                justify-content: flex-start;
            }
            .docs-toc platform-button.nested {
                padding-inline-start: calc(var(--space-3) + var(--space-4));
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
                font-family: var(--font-mono);
                font-size: 0.9em;
                background: var(--glass-tint-medium);
                padding: 0.1em 0.35em;
                border-radius: var(--radius-sm);
            }
            .docs-md pre {
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
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
                border: 1px solid var(--border-subtle);
                padding: var(--space-2);
                text-align: left;
            }
            .docs-md th {
                background: var(--bg-elevated);
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
        `,
    ];
    private _docsOp: OpController;

    constructor() {
        super();
        this.size = 'full';
        this.language = 'python';
        this.documentationPerspective = 'editor';
        this._search = '';
        this._docsOp = this.useOp('flows/code_documentation');
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('open') && this.open) {
            this._search = '';
            void this._loadDocumentation();
        }
    }

    override updated(changed: PropertyValues<this>): void {
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

    _onSearchInput(e: CustomEvent) {
        this._search = typeof e.detail?.value === 'string' ? e.detail.value : '';
    }

    _scrollToTarget(item: any) {
        const main = this.renderRoot?.querySelector('.docs-main .docs-md');
        if (!main) {
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

    _filteredToc(toc: any) {
        const q = _lower(this._search);
        if (q.length === 0) {
            return toc;
        }
        return toc.filter((it: any) => _lower(it.text).indexOf(q) >= 0);
    }

    _setLanguage(language: any) {
        this.language = normalizeFlowCodeLanguage(language) as string;
    }

    _renderLanguageSegment() {
        const current = this._documentationLanguage();
        return html`
            <flows-code-language-segment
                full-width
                .value=${current}
                aria-label=${this.t('code_workbench.language_aria')}
                @change=${(e: CustomEvent) => this._setLanguage(e.detail.value)}
            ></flows-code-language-segment>
        `;
    }

    override renderHeader() {
        return `${this.t('code_docs_modal.title')} · ${flowCodeLanguageLabel(this._documentationLanguage())}`;
    }

    override renderBody() {
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
                <aside class="docs-sidebar content-panel" aria-label=${this.t('code_docs_modal.toc_aria')}>
                    <div class="docs-sidebar-top">
                        ${this._renderLanguageSegment()}
                        <platform-modal-search-field
                            layout="fill"
                            .value=${this._search}
                            placeholder=${this.t('code_docs_modal.search_placeholder')}
                            @change=${this._onSearchInput}
                        ></platform-modal-search-field>
                    </div>
                    <nav class="docs-toc">
                        ${shown.length === 0
                            ? html`<div class="docs-toc-empty">${this.t('code_docs_modal.toc_empty')}</div>`
                            : shown.map(
                                (it: any) => html`
                                <platform-button
                                    variant="ghost"
                                    density=${it.level >= 3 ? 'dense' : 'compact'}
                                    class=${it.level >= 3 ? 'nested' : ''}
                                    @click=${() => this._scrollToTarget(it)}
                                >${it.text}</platform-button>
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
