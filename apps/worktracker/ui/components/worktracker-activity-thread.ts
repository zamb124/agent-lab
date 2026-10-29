/**
 * WorktrackerActivityThread — comments timeline + inline composer.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

interface WorkItemComment {
    author?: { actor_kind?: string; user_id?: unknown };
    created_at?: unknown;
    text?: unknown;
    files?: unknown[];
    [key: string]: unknown;
}
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { buildWorkItemFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { worktrackerDetailContentStyles } from '../styles/worktracker-detail.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-file-attachments.js';

export class WorktrackerActivityThread extends PlatformElement {
    static i18nNamespace = 'worktracker';
    declare comments: WorkItemComment[];
    declare commentDraft: string;
    declare commentFiles: unknown[];
    declare workItemId: string;
    declare locale: string;
    declare embedded: boolean;
    declare subtitle: string;


    static override properties = {
        comments: { type: Array, attribute: false },
        commentDraft: { type: String, attribute: 'comment-draft' },
        commentFiles: { type: Array, attribute: false },
        workItemId: { type: String, attribute: 'work-item-id' },
        locale: { type: String },
        embedded: { type: Boolean },
        /** Подпись под заголовком (например, что Activity — внутренние заметки HITL). */
        subtitle: { type: String },
    };

    static override styles = [
        PlatformElement.styles,
        worktrackerDetailContentStyles,
        css`
            :host {
                display: block;
                min-width: 0;
                height: auto;
            }
            :host([embedded]) .wt-activity {
                padding-top: 0;
                border-top: none;
                margin-top: 0;
                gap: var(--space-2);
            }
            :host([embedded]) .wt-composer-hint {
                margin-top: calc(-1 * var(--space-1));
            }
            .wt-comment-files {
                margin-top: var(--space-2);
            }
            .wt-composer-files {
                margin-top: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.comments = [];
        this.commentDraft = '';
        this.commentFiles = [];
        this.workItemId = '';
        this.locale = 'ru';
        this.embedded = false;
        this.subtitle = '';
    }

    private _formatTimestamp(value: unknown) {
        if (typeof value !== 'string' || value.length === 0) {
            return '';
        }
        return formatPlatformDateTime(value, this.locale);
    }

    private _onCommentChange(event: CustomEvent<{ value?: unknown }>) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this.emit('wt-comment-change', { value });
    }

    private _onCommentKeydown(event: KeyboardEvent) {
        if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
            event.preventDefault();
            this.emit('wt-comment-submit', null);
        }
    }

    private _submit() {
        this.emit('wt-comment-submit', null);
    }

    private _uploadSpecJson() {
        return buildWorkItemFileCreateSpecJson({ workItemId: this.workItemId });
    }

    private _commentFiles(comment: WorkItemComment) {
        if (Array.isArray(comment.files)) {
            return comment.files;
        }
        return [];
    }

    private _canSubmit() {
        const text = typeof this.commentDraft === 'string' ? this.commentDraft.trim() : '';
        const files = Array.isArray(this.commentFiles) ? this.commentFiles : [];
        return text.length > 0 || files.length > 0;
    }

    private _renderComments() {
        const rows = Array.isArray(this.comments) ? this.comments : [];
        if (rows.length === 0) {
            return html`<div class="wt-activity-empty">${this.t('detail_page.no_comments')}</div>`;
        }
        return html`
            <div class="wt-comment-list">
                ${rows.map((comment) => {
                    const author = comment.author;
                    const userId = author && author.actor_kind === 'user' && typeof author.user_id === 'string'
                        ? author.user_id
                        : '';
                    const createdAt = this._formatTimestamp(comment.created_at);
                    const files = this._commentFiles(comment);
                    return html`
                        <div class="wt-comment-row">
                            ${userId
                                ? html`<platform-user-chip user-id=${userId} size="sm" .interactive=${false}></platform-user-chip>`
                                : nothing}
                            <div class="wt-comment-body">
                                ${createdAt ? html`<div class="wt-comment-meta">${createdAt}</div>` : nothing}
                                <div class="wt-comment-text">${comment.text}</div>
                                ${files.length > 0 ? html`
                                    <div class="wt-comment-files">
                                        <platform-file-attachments
                                            readonly
                                            .files=${files}
                                            open-source="worktracker_comment_files"
                                        ></platform-file-attachments>
                                    </div>
                                ` : nothing}
                            </div>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    override render() {
        const canSubmit = this._canSubmit();
        return html`
            <section class="wt-activity">
                <h3 class="wt-activity-title">${this.t('detail_page.section_activity')}</h3>
                ${typeof this.subtitle === 'string' && this.subtitle.trim() !== ''
                    ? html`<p class="wt-activity-subtitle">${this.subtitle}</p>`
                    : nothing}
                ${this._renderComments()}
                <div class="wt-composer">
                    <platform-field
                        class="wt-composer-field"
                        type="text"
                        mode="edit"
                        pill-embed
                        pill-density="dense"
                        data-canon="composer"
                        .label=${''}
                        .placeholder=${this.t('detail_page.comment_placeholder')}
                        .value=${this.commentDraft}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onCommentChange(e)}
                        @keydown=${(e: KeyboardEvent) => this._onCommentKeydown(e)}
                    ></platform-field>
                    <button
                        type="button"
                        class="wt-composer-send"
                        ?disabled=${!canSubmit}
                        aria-label=${this.t('detail_panel.add_comment')}
                        @click=${() => this._submit()}
                    >
                        <platform-icon name="send" size="18"></platform-icon>
                    </button>
                </div>
                <div class="wt-composer-files">
                    <platform-file-attachments
                        compact
                        .files=${Array.isArray(this.commentFiles) ? this.commentFiles : []}
                        .uploadSpec=${this._uploadSpecJson()}
                        open-source="worktracker_comment_composer"
                        @files-change=${(e: CustomEvent<{ files?: unknown }>) => {
                            const files = e.detail && Array.isArray(e.detail.files) ? e.detail.files : [];
                            this.emit('wt-comment-files-change', { files });
                        }}
                    ></platform-file-attachments>
                </div>
                <div class="wt-composer-hint">${this.t('detail_page.comment_hint')}</div>
            </section>
        `;
    }
}

customElements.define('worktracker-activity-thread', WorktrackerActivityThread);
