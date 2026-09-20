/**
 * История версий страницы: список ревизий и сравнение с текущим текстом.
 *
 * Дифф считается по строкам markdown, а не по узлам ProseMirror: markdown
 * читаем человеком, и именно его сравнивают глазами при откате.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';

/**
 * Построчный дифф: строки, которых нет во второй версии, помечаются как
 * удалённые, новые — как добавленные. Порядок сохраняется по текущей версии.
 *
 * @param {string} before
 * @param {string} after
 * @returns {{ kind: 'same' | 'added' | 'removed', text: string }[]}
 */
export function buildLineDiff(before, after) {
    const beforeLines = before.split('\n');
    const afterLines = after.split('\n');
    const beforeCounts = new Map();
    for (const line of beforeLines) {
        beforeCounts.set(line, (beforeCounts.get(line) ?? 0) + 1);
    }
    const afterCounts = new Map();
    for (const line of afterLines) {
        afterCounts.set(line, (afterCounts.get(line) ?? 0) + 1);
    }

    const rows = [];
    for (const line of beforeLines) {
        const inAfter = (afterCounts.get(line) ?? 0) > 0;
        if (inAfter) {
            afterCounts.set(line, afterCounts.get(line) - 1);
            rows.push({ kind: 'same', text: line });
        } else {
            rows.push({ kind: 'removed', text: line });
        }
    }
    for (const line of afterLines) {
        if ((beforeCounts.get(line) ?? 0) > 0) {
            beforeCounts.set(line, beforeCounts.get(line) - 1);
            continue;
        }
        rows.push({ kind: 'added', text: line });
    }
    return rows.filter((row) => row.text.trim() !== '' || row.kind !== 'same');
}

export class WikiHistoryPage extends PlatformPage {
    static i18nNamespace = 'wiki';

    static properties = {
        pageId: { type: String, attribute: 'page-id' },
        _selectedRevisionId: { state: true },
        _diffRows: { state: true },
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
                grid-template-columns: 22rem minmax(0, 1fr);
                height: 100%;
            }

            .list {
                border-right: 1px solid var(--glass-border-subtle);
                overflow-y: auto;
                padding: var(--space-4) var(--space-3);
            }

            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-3);
            }

            .title {
                margin: 0;
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .revision {
                display: block;
                width: 100%;
                padding: var(--space-2) var(--space-3);
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

            .revision-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }

            .revision-meta {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .diff {
                overflow-y: auto;
                padding: var(--space-5);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.6;
            }

            .diff-line {
                padding: 1px var(--space-2);
                white-space: pre-wrap;
                overflow-wrap: anywhere;
            }

            .diff-line[data-kind='added'] {
                background: color-mix(in srgb, var(--success) 14%, transparent);
                color: var(--success);
            }

            .diff-line[data-kind='removed'] {
                background: color-mix(in srgb, var(--error) 14%, transparent);
                color: var(--error);
            }

            .state {
                padding: var(--space-8);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.pageId = '';
        this._selectedRevisionId = '';
        this._diffRows = [];
        this._revisions = this.useOp('wiki/revisions');
        this._revisionRead = this.useOp('wiki/revision_read');
        this._revisionRestore = this.useOp('wiki/revision_restore');
        this._markdown = this.useOp('wiki/page_markdown');
        this._locale = this.select((state) => state.i18n.locale);
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('pageId') && this.pageId !== '') {
            void this._revisions.run({ wiki_page_id: this.pageId });
            void this._markdown.run({ wiki_page_id: this.pageId });
        }
    }

    _revisionItems() {
        const state = this._revisions.lastResult;
        if (state === null) {
            return [];
        }
        if (typeof state !== 'object' || !Array.isArray(state.items)) {
            throw new Error('wiki revisions: lastResult.items required');
        }
        return state.items;
    }

    async _selectRevision(revisionId) {
        this._selectedRevisionId = revisionId;
        const revision = await this._revisionRead.run({ wiki_revision_id: revisionId });
        const current = this._markdown.state.text_markdown;
        const currentText = typeof current === 'string' ? current : '';
        const revisionText = typeof revision.text_markdown === 'string' ? revision.text_markdown : '';
        this._diffRows = buildLineDiff(revisionText, currentText);
    }

    async _restore() {
        const confirmed = await platformConfirm(this.t('history.restore_confirm_body'), {
            title: this.t('history.restore_confirm_title'),
        });
        if (!confirmed) {
            return;
        }
        await this._revisionRestore.run({ wiki_revision_id: this._selectedRevisionId });
        this.navigate('wiki_page', { pageId: this.pageId });
    }

    render() {
        const revisions = this._revisionItems();
        return html`
            <div class="layout">
                <div class="list">
                    <div class="head">
                        <h1 class="title">${this.t('history.title')}</h1>
                        <platform-button
                            variant="ghost"
                            size="sm"
                            data-wiki-history-back
                            @click=${() => this.navigate('wiki_page', { pageId: this.pageId })}
                        >${this.t('history.back_to_page')}</platform-button>
                    </div>
                    ${revisions.length === 0
                        ? html`<div class="state">${this.t('history.empty')}</div>`
                        : revisions.map((revision) => html`
                              <button
                                  class="revision ${revision.wiki_revision_id === this._selectedRevisionId ? 'is-selected' : ''}"
                                  type="button"
                                  data-wiki-revision=${revision.wiki_revision_id}
                                  @click=${() => this._selectRevision(revision.wiki_revision_id)}
                              >
                                  <div class="revision-title">
                                      ${revision.title === '' ? this.t('page.untitled') : revision.title}
                                  </div>
                                  <div class="revision-meta">
                                      ${formatPlatformDateTime(new Date(revision.created_at), this._locale.value)}
                                  </div>
                              </button>
                          `)}
                </div>
                <div class="diff">${this._renderDiff()}</div>
            </div>
        `;
    }

    _renderDiff() {
        if (this._selectedRevisionId === '') {
            return html`<div class="state">${this.t('history.current')}</div>`;
        }
        if (this._revisionRead.busy) {
            return html`<div class="state"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        return html`
            <platform-button variant="primary" size="sm" data-wiki-restore @click=${this._restore}>
                ${this.t('history.restore')}
            </platform-button>
            ${this._diffRows.map((row) => html`
                <div class="diff-line" data-kind=${row.kind}>${row.text}</div>
            `)}
        `;
    }
}

customElements.define('wiki-history-page', WikiHistoryPage);
