/**
 * Что не перенеслось из markdown-файла.
 *
 * Окно открывается только когда расхождения есть. Иначе импорт молча менял бы
 * содержимое, и пользователь узнавал бы о потере вёрстки случайно, через месяц.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class WikiImportReportModal extends PlatformModal {
    static modalKind = 'wiki.import_report';
    static i18nNamespace = 'wiki';

    static properties = {
        /** `{ kind, detail, line }[]` из ответа импорта. */
        notices: { attribute: false },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .intro {
                margin-bottom: var(--space-4);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            .notice {
                display: grid;
                grid-template-columns: auto minmax(0, 1fr);
                gap: var(--space-2) var(--space-3);
                padding: var(--space-3) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .notice:last-of-type {
                border-bottom: none;
            }

            .notice-kind {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
            }

            .notice-detail {
                color: var(--text-primary);
                font-size: var(--text-sm);
                overflow-wrap: anywhere;
            }

            .notice-line {
                grid-column: 2;
                color: var(--text-tertiary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.notices = [];
    }

    _items() {
        return Array.isArray(this.notices) ? this.notices : [];
    }

    renderHeader() {
        return this.t('import_report.title');
    }

    renderBody() {
        const items = this._items();
        return html`
            <div class="intro">${this.t('import_report.intro', { count: items.length })}</div>
            ${items.map((notice) => html`
                <div class="notice" data-wiki-notice=${notice.kind}>
                    <span class="notice-kind">${this.t(`import_report.kind.${notice.kind}`)}</span>
                    <span class="notice-detail">${notice.detail}</span>
                    ${typeof notice.line === 'number'
                        ? html`<span class="notice-line">
                              ${this.t('import_report.line', { line: notice.line })}
                          </span>`
                        : ''}
                </div>
            `)}
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="primary" data-wiki-report-close @click=${() => this.close()}>
                ${this.t('import_report.close')}
            </platform-button>
        `;
    }
}

customElements.define('wiki-import-report-modal', WikiImportReportModal);
registerModalKind(WikiImportReportModal.modalKind, 'wiki-import-report-modal');
