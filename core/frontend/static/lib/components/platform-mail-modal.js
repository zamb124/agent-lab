/**
 * Platform mail workspace — fullscreen modal (кроссервисный, как calendar).
 * modalKind: platform.mail
 */
import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from './glass-modal.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import './platform-icon.js';
import './platform-button.js';
import './platform-spinner.js';
import './platform-file-attachments.js';
import './fields/platform-field.js';
import './platform-user-chip.js';
import './platform-markdown-editor.js';
import './platform-mail-calendar-rail.js';
import './platform-palette-color-picker.js';
import { sanitizeMarkdownEditorHtml } from './platform-markdown-editor.js';
import { flowsChatMarkdownToHtml } from '../chat/markdown.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { platformConfirm } from './platform-confirm-modal.js';
import { MAIL_EVENTS } from '../events/reducers/mail.js';
import { CALENDAR_EVENTS } from '../events/reducers/calendar.js';
import { TEAM_EVENTS } from '../events/reducers/team.js';
import {
    formatPlatformDate,
    formatPlatformDateTime,
    formatPlatformTime,
} from '../utils/format-platform-date.js';
import { formatFileSize } from '../utils/format-file-size.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import { hueFromString, initialsFromName } from '../utils/hash-string.js';
import { COLOR_PALETTE } from '../utils/color-palette.js';
import { escapeHtml } from '../utils/escape-html.js';
import {
    findThreadByUid,
    findThreadMessageByMessageId,
    groupMailThreads,
    mailReplyPreviewText,
    normalizeMailSubject,
} from '../utils/mail-threads.js';

function paletteKeyFromPickerValue(value) {
    if (typeof value !== 'string' || !value.trim()) {
        throw new Error('platform-mail-modal: calendar_color required');
    }
    const normalized = value.trim().toLowerCase();
    const byKey = COLOR_PALETTE.find((entry) => entry.key === normalized);
    if (byKey) return byKey.key;
    const byDot = COLOR_PALETTE.find((entry) => entry.dot.toLowerCase() === normalized);
    if (byDot) return byDot.key;
    throw new Error(`platform-mail-modal: unknown calendar_color=${value}`);
}

const FOLDER_ROLE_META = Object.freeze({
    inbox: Object.freeze({ key: 'folder_inbox', icon: 'inbox' }),
    sent: Object.freeze({ key: 'folder_sent', icon: 'send' }),
    drafts: Object.freeze({ key: 'folder_drafts', icon: 'edit' }),
    trash: Object.freeze({ key: 'folder_trash', icon: 'trash' }),
    junk: Object.freeze({ key: 'folder_junk', icon: 'trash' }),
    archive: Object.freeze({ key: 'folder_archive', icon: 'folder' }),
});

function parseToList(value) {
    if (typeof value !== 'string' || !value.trim()) {
        return [];
    }
    return value.split(/[,;]/).map((part) => part.trim()).filter((part) => part.length > 0);
}

function parseMailAddress(raw) {
    if (typeof raw !== 'string' || !raw.trim()) {
        return Object.freeze({ display: '', email: '', seed: '?' });
    }
    const trimmed = raw.trim();
    const angled = trimmed.match(/^(.*?)\s*<([^>]+)>\s*$/);
    if (angled) {
        const name = angled[1].replace(/^["']|["']$/g, '').trim();
        const email = angled[2].trim();
        const display = name.length > 0 ? name : email;
        return Object.freeze({ display, email, seed: display });
    }
    return Object.freeze({ display: trimmed, email: trimmed, seed: trimmed });
}

function subjectWithPrefix(subject, prefix) {
    const base = typeof subject === 'string' ? subject.trim() : '';
    if (!base) return `${prefix} `;
    if (base.toLowerCase().startsWith(prefix.toLowerCase())) return base;
    return `${prefix} ${base}`;
}

function messagesCountKey(count) {
    if (count === 1) return 'messages_count_one';
    return 'messages_count_other';
}

function unreadCountKey(count) {
    if (count === 1) return 'unread_count_one';
    return 'unread_count_other';
}

/** Сегодня → время; этот год → день+месяц; иначе дата с годом. */
function formatMailListDate(input, locale) {
    if (input == null || input === '') {
        return '';
    }
    const date = input instanceof Date ? input : new Date(input);
    if (Number.isNaN(date.getTime())) {
        return '';
    }
    const now = new Date();
    const sameDay = date.getFullYear() === now.getFullYear()
        && date.getMonth() === now.getMonth()
        && date.getDate() === now.getDate();
    if (sameDay) {
        return formatPlatformTime(date, locale);
    }
    if (date.getFullYear() === now.getFullYear()) {
        return formatPlatformDate(date, locale, { day: 'numeric', month: 'short' });
    }
    return formatPlatformDate(date, locale, { day: 'numeric', month: 'short', year: 'numeric' });
}

export class PlatformMailModal extends PlatformModal {
    static modalKind = 'platform.mail';
    static i18nNamespace = 'mail';

    static properties = {
        ...PlatformModal.properties,
        openSettings: { type: Boolean },
        _adminDraft: { state: true },
        _createLocalPart: { state: true },
        _createUserId: { state: true },
        _assignDrafts: { state: true },
        _mobilePane: { state: true },
        _composeOpen: { state: true },
        _composeExpanded: { state: true },
        _composePos: { state: true },
        _composeSize: { state: true },
        _composeDragging: { state: true },
        _composeResizing: { state: true },
        _listQuery: { state: true },
        _quickReplyText: { state: true },
        _expandedThreadIds: { state: true },
        _createKind: { state: true },
        _memberDraftUserId: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host {
                /* layout tokens: --mail-* from tokens.css */
            }

            :host([open]) .modal-overlay {
                padding: 0 !important;
                inset: 0 !important;
            }

            :host([open]) .modal,
            :host([open]) .modal.full,
            :host([open]) .modal.fullscreen {
                position: fixed !important;
                inset: 0 !important;
                left: 0 !important;
                top: 0 !important;
                width: 100vw !important;
                max-width: 100vw !important;
                height: 100dvh !important;
                max-height: 100dvh !important;
                min-height: 100dvh !important;
                border-radius: 0 !important;
                margin: 0 !important;
                transform: none !important;
                --modal-content-inset: 0;
                --modal-content-radius: 0;
            }

            :host([open]) .modal .modal-content,
            :host([open]) .modal.full .modal-content,
            :host([open]) .modal.fullscreen .modal-content {
                padding: 0 !important;
                margin: 0 !important;
                border-radius: 0 !important;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: 100%;
            }

            :host([open]) .modal .modal-header,
            :host([open]) .modal.fullscreen .modal-header {
                display: none !important;
            }

            @media (max-width: 768px) {
                :host([open]) .modal,
                :host([open]) .modal.full,
                :host([open]) .modal.fullscreen {
                    width: 100vw !important;
                    max-width: 100vw !important;
                    height: 100dvh !important;
                    max-height: 100dvh !important;
                    border-radius: 0 !important;
                }
            }

            .mail-shell-wrap {
                position: relative;
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                background: var(--bg-primary);
            }
            .mail-shell {
                display: grid;
                grid-template-columns:
                    var(--mail-rail-width, 64px)
                    var(--mail-nav-width, 260px)
                    var(--mail-list-width, 400px)
                    minmax(0, 1fr);
                min-height: 0;
                flex: 1;
                background: var(--bg-primary);
                color: var(--text-primary);
            }
            .mail-nav,
            .mail-list,
            .mail-thread {
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .mail-list {
                width: var(--mail-list-width, 400px);
                min-width: 0;
                overflow: hidden;
                background: var(--bg-primary);
                border-right: 1px solid var(--border-subtle);
            }
            platform-mail-calendar-rail {
                min-height: 0;
            }
            .mail-nav {
                padding: var(--space-5) var(--space-4);
                padding-bottom: max(var(--space-5), env(safe-area-inset-bottom, 0px));
                gap: var(--space-4);
                background: var(--bg-surface);
                border-right: 1px solid var(--border-subtle);
                overflow: hidden;
            }
            .nav-account {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .nav-account-label {
                font-size: 0.75rem;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--text-tertiary);
            }
            .nav-account-email {
                font-size: 0.875rem;
                font-weight: 600;
                color: var(--text-primary);
                word-break: break-all;
                line-height: 1.35;
            }
            .nav-compose {
                width: 100%;
            }
            .nav-section-title {
                font-size: 0.75rem;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--text-tertiary);
                padding: 0 var(--space-2);
            }
            .nav-folders {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                flex: 1;
                min-height: 0;
                overflow: auto;
            }
            .folder-btn {
                display: grid;
                grid-template-columns: 20px minmax(0, 1fr) auto;
                align-items: center;
                gap: var(--space-3);
                min-height: 44px;
                padding: 0 var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                text-align: left;
                font: inherit;
                transition: background 0.15s ease, color 0.15s ease;
            }
            .folder-btn:hover {
                background: color-mix(in srgb, var(--accent) 10%, transparent);
                color: var(--text-primary);
            }
            .folder-btn.active {
                background: var(--accent-subtle);
                color: var(--text-primary);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
            }
            .folder-icon {
                width: 20px;
                height: 20px;
                display: grid;
                place-items: center;
                background: transparent;
                color: inherit;
            }
            .folder-btn.active .folder-icon {
                color: var(--accent);
            }
            .folder-label {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-weight: 500;
            }
            .folder-unseen {
                min-width: 1.25rem;
                padding: 0 6px;
                border-radius: var(--radius-full, 999px);
                background: color-mix(in srgb, var(--mail-unread-dot, var(--accent-secondary)) 18%, transparent);
                color: var(--mail-unread-dot, var(--accent-secondary));
                font-size: 0.6875rem;
                font-weight: 700;
                line-height: 1.4;
                text-align: center;
                font-variant-numeric: tabular-nums;
            }
            .folder-btn.active .folder-unseen {
                background: color-mix(in srgb, var(--mail-unread-dot, var(--accent-secondary)) 24%, transparent);
            }
            .upcoming {
                margin-top: auto;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding-top: var(--space-4);
                border-top: 1px solid var(--border-subtle);
                flex-shrink: 0;
            }
            .upcoming-title {
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .upcoming-item {
                display: flex;
                flex-direction: column;
                gap: 2px;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
                color: inherit;
                cursor: pointer;
                text-align: left;
                font: inherit;
            }
            .upcoming-item:hover {
                border-color: color-mix(in srgb, var(--accent) 40%, transparent);
            }
            .upcoming-time {
                font-size: 0.75rem;
                color: var(--text-secondary);
            }
            .mail-thread {
                background: var(--bg-primary);
                min-width: 0;
                min-height: 0;
                overflow: hidden;
            }
            .mail-list-header {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4) var(--space-4) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--bg-surface);
            }
            .mail-list-header-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .list-search {
                width: 100%;
                height: 36px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                padding: 0 var(--space-3);
                background: var(--bg-elevated);
                color: var(--text-primary);
                font: inherit;
                font-size: 0.875rem;
            }
            .list-search:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-subtle);
            }
            .mail-thread-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-5);
                border-bottom: 1px solid var(--border-subtle);
                min-height: var(--mail-action-bar-height);
                background: var(--bg-surface);
            }
            .thread-back {
                display: none;
            }
            .thread-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-wrap: wrap;
            }
            .list-header-copy {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }
            .list-header-title {
                font-size: 1.0625rem;
                font-weight: 650;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .list-header-meta {
                font-size: 0.8125rem;
                color: var(--text-tertiary);
            }
            .mail-list-body,
            .mail-thread-scroll {
                overflow: auto;
                flex: 1;
                min-height: 0;
            }
            .pane-loading {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                min-height: 160px;
                padding: var(--space-6);
                color: var(--text-tertiary);
                font-size: 0.875rem;
            }
            .msg-row {
                display: grid;
                grid-template-columns: 10px 40px minmax(0, 1fr) auto;
                column-gap: var(--space-3);
                row-gap: 0;
                align-items: start;
                width: 100%;
                box-sizing: border-box;
                min-height: var(--mail-row-height, 72px);
                padding: var(--space-3) var(--space-4);
                border: none;
                border-bottom: 1px solid var(--border-subtle);
                background: transparent;
                color: inherit;
                cursor: pointer;
                text-align: left;
                font: inherit;
                transition: background 0.12s ease;
            }
            .msg-row:hover {
                background: color-mix(in srgb, var(--accent) 8%, transparent);
            }
            .msg-row.active {
                background: var(--accent-subtle);
                box-shadow: inset 3px 0 0 var(--accent);
            }
            .msg-row .msg-from {
                font-weight: 500;
                color: var(--text-secondary);
            }
            .msg-row .msg-subject {
                font-weight: 400;
                color: var(--text-tertiary);
            }
            .msg-row.unread .msg-from,
            .msg-row.unread .msg-subject {
                font-weight: 700;
                color: var(--text-primary);
            }
            .msg-row.unread {
                background: color-mix(in srgb, var(--accent-secondary) 6%, transparent);
            }
            /* grid-column только внутри .msg-row — иначе в .thread-sender аватар уезжает
               во 2-ю колонку, а имя/email сжимаются в 40px (Vic… / zam…). */
            .msg-unread-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                margin-top: 14px;
                justify-self: center;
                background: var(--mail-unread-dot, var(--accent-secondary));
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--mail-unread-dot, var(--accent-secondary)) 35%, transparent);
            }
            .msg-row .msg-unread-dot {
                grid-column: 1;
            }
            /* Не использовать [hidden]/display:none — иначе ячейка grid пропадает и колонки съезжают. */
            .msg-unread-dot.is-read {
                visibility: hidden;
            }
            .msg-avatar {
                width: 36px;
                height: 36px;
                border-radius: 50%;
                display: grid;
                place-items: center;
                flex-shrink: 0;
                color: var(--text-inverse);
                font-size: 0.75rem;
                font-weight: 700;
                margin-top: 2px;
            }
            .msg-row .msg-avatar {
                grid-column: 2;
            }
            .msg-main {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
                overflow: hidden;
            }
            .msg-row .msg-main {
                grid-column: 3;
            }
            .msg-date {
                grid-column: 4;
                margin-top: 2px;
                font-size: 0.75rem;
                font-weight: 500;
                color: var(--text-tertiary);
                white-space: nowrap;
                font-variant-numeric: tabular-nums;
                justify-self: end;
            }
            .msg-row.unread .msg-date {
                color: var(--text-secondary);
                font-weight: 650;
            }
            .msg-top {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .msg-from {
                flex: 1 1 auto;
                min-width: 0;
                font-weight: 650;
                font-size: 0.875rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .msg-indicators {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                flex-shrink: 0;
                color: var(--text-tertiary);
            }
            .msg-attach-count {
                font-size: 0.6875rem;
                font-weight: 600;
                color: var(--text-tertiary);
            }
            .msg-subject {
                color: var(--text-primary);
                font-weight: 500;
                font-size: 0.875rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .msg-snippet {
                color: var(--text-tertiary);
                font-size: 0.8125rem;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .msg-count {
                color: var(--text-tertiary);
                font-weight: 500;
                font-size: 0.8125rem;
                flex-shrink: 0;
            }
            .msg-avatars {
                position: relative;
                width: 40px;
                height: 36px;
                grid-column: 2;
            }
            .msg-avatars .msg-avatar {
                position: absolute;
                top: 0;
                left: 0;
                width: 32px;
                height: 32px;
                font-size: 0.6875rem;
                border: 2px solid var(--bg-primary, var(--bg-surface));
            }
            .msg-avatars .msg-avatar:nth-child(2) {
                left: 12px;
                z-index: 1;
            }
            .msg-avatars .msg-avatar:nth-child(3) {
                left: 24px;
                z-index: 2;
            }
            .thread-row-wrap {
                border-bottom: 1px solid var(--border-subtle);
            }
            .thread-row-wrap .msg-row {
                border-bottom: none;
            }
            .thread-expand {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                margin: 0;
                padding: 0;
                border: none;
                border-radius: var(--radius-sm, 6px);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                flex-shrink: 0;
            }
            .thread-expand:hover,
            .msg-row.active .thread-expand {
                background: color-mix(in srgb, var(--accent) 10%, transparent);
                color: var(--text-primary);
            }
            .thread-expand platform-icon {
                transition: transform 0.15s ease;
            }
            .thread-expand[aria-expanded='true'] platform-icon {
                transform: rotate(180deg);
            }
            .thread-preview {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4) var(--space-3) 58px;
            }
            .thread-preview-loading {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: 0.8125rem;
            }
            .thread-preview-item {
                display: flex;
                gap: var(--space-2);
                align-items: flex-start;
                max-width: 100%;
            }
            .thread-preview-item.mine {
                align-self: flex-end;
                flex-direction: row-reverse;
            }
            .thread-preview-item.theirs {
                align-self: flex-start;
            }
            .thread-preview-item .msg-avatar {
                width: 28px;
                height: 28px;
                font-size: 0.625rem;
                margin-top: 0;
                flex-shrink: 0;
            }
            .thread-preview-bubble {
                min-width: 0;
                max-width: min(420px, 100%);
                padding: 6px 10px;
                border-radius: 12px;
                background: var(--mail-bubble-theirs-bg, var(--bg-elevated));
                border: 1px solid var(--border-subtle);
            }
            .thread-preview-item.mine .thread-preview-bubble {
                background: var(--mail-bubble-mine-bg, color-mix(in srgb, var(--accent) 14%, var(--bg-elevated)));
            }
            .thread-preview-from {
                font-size: 0.75rem;
                font-weight: 650;
                color: var(--text-secondary);
            }
            .thread-preview-text {
                font-size: 0.8125rem;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .chat-stream {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4) var(--space-5) var(--space-5);
            }
            .chat-bubble-row {
                display: flex;
                gap: var(--space-2);
                align-items: flex-end;
                max-width: min(720px, 100%);
            }
            .chat-bubble-row.mine {
                align-self: flex-end;
                flex-direction: row-reverse;
            }
            .chat-bubble-row.theirs {
                align-self: flex-start;
            }
            .chat-bubble {
                min-width: 0;
                max-width: 100%;
                padding: 10px 14px;
                border-radius: 16px;
                border: 1px solid var(--border-subtle);
                background: var(--mail-bubble-theirs-bg, var(--bg-elevated));
            }
            .chat-bubble-row.mine .chat-bubble {
                background: var(--mail-bubble-mine-bg, color-mix(in srgb, var(--accent) 14%, var(--bg-elevated)));
                border-color: color-mix(in srgb, var(--accent) 28%, var(--border-subtle));
            }
            .chat-bubble-meta {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                margin-bottom: 6px;
            }
            .chat-bubble-from {
                font-size: 0.8125rem;
                font-weight: 650;
                color: var(--text-primary);
            }
            .chat-bubble-time {
                font-size: 0.75rem;
                color: var(--text-tertiary);
            }
            .chat-bubble-reply {
                margin-left: auto;
                flex-shrink: 0;
            }
            .chat-bubble-row.mine .chat-bubble-reply {
                margin-left: 0;
                margin-right: auto;
            }
            .chat-bubble-row.reply-target-flash .chat-bubble {
                outline: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
                outline-offset: 2px;
                transition: outline-color 0.6s ease;
            }
            .mail-reply-quote {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: 2px;
                width: 100%;
                margin: 0 0 8px;
                padding: 6px 10px;
                border: none;
                border-left: 3px solid var(--accent);
                border-radius: 0 8px 8px 0;
                background: color-mix(in srgb, var(--glass-solid-soft, var(--bg-surface)) 78%, var(--accent) 8%);
                color: var(--text-secondary);
                text-align: left;
                cursor: pointer;
                font: inherit;
            }
            .mail-reply-quote:hover {
                background: color-mix(in srgb, var(--glass-solid-soft, var(--bg-surface)) 70%, var(--accent) 14%);
            }
            .mail-reply-quote .who {
                font-size: 0.75rem;
                font-weight: 650;
                color: var(--text-primary);
                line-height: 1.2;
            }
            .mail-reply-quote .preview {
                font-size: 0.75rem;
                color: var(--text-tertiary);
                line-height: 1.35;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            .compose-reply-mode {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 6px 10px;
                margin: 0 var(--space-4) var(--space-2);
                border-left: 3px solid var(--accent);
                border-radius: 0 8px 8px 0;
                background: color-mix(in srgb, var(--bg-elevated) 85%, var(--accent) 10%);
                color: var(--text-secondary);
                font-size: 0.8125rem;
            }
            .compose-reply-mode-label {
                min-width: 0;
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .compose-reply-mode-label .who {
                font-weight: 650;
                color: var(--text-primary);
            }
            .chat-bubble .thread-body-text {
                padding: 0;
                max-width: none;
            }
            .chat-bubble .thread-attachments {
                padding: var(--space-3) 0 0;
            }
            .folder-chip {
                display: inline-flex;
                align-items: center;
                height: 22px;
                padding: 0 8px;
                border-radius: var(--radius-full, 999px);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
                color: var(--text-secondary);
                font-size: 0.6875rem;
                font-weight: 600;
                white-space: nowrap;
            }
            .att-badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                border-radius: var(--radius-full, 999px);
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--text-secondary);
            }
            .thread-meta {
                padding: var(--space-5) var(--space-5) var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
            }
            .thread-subject {
                font-size: 1.375rem;
                font-weight: 650;
                line-height: 1.25;
                letter-spacing: -0.01em;
            }
            .thread-subject-meta {
                font-size: 0.8125rem;
                font-weight: 500;
                color: var(--text-tertiary);
                margin-top: 4px;
            }
            .thread-sender {
                display: grid;
                grid-template-columns: 40px minmax(0, 1fr);
                gap: var(--space-3);
                align-items: start;
            }
            .thread-sender .msg-avatar {
                grid-column: 1;
                margin-top: 0;
            }
            .thread-sender-copy {
                grid-column: 2;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .thread-sender-copy .msg-from {
                flex: none;
                white-space: normal;
                overflow: visible;
                text-overflow: unset;
            }
            .thread-people {
                font-size: 0.8125rem;
                color: var(--text-secondary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .thread-date {
                font-size: 0.8125rem;
                color: var(--text-tertiary);
            }
            .thread-body-text {
                padding: var(--space-5);
                line-height: 1.6;
                font-size: 0.9375rem;
                max-width: 72ch;
            }
            .thread-body-text p {
                margin: 0 0 var(--space-3);
            }
            .thread-body-text p:last-child {
                margin-bottom: 0;
            }
            platform-markdown-editor {
                flex: 1 1 auto;
                min-height: 0;
                margin-top: 0;
                border: none;
                border-radius: 0;
                border-top: 1px solid var(--border-subtle);
                --markdown-editor-min-height: 0;
                --markdown-editor-body-min-height: 72px;
                --markdown-editor-body-max-height: none;
            }
            .thread-attachments {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: 0 var(--space-5) var(--space-5);
            }
            .thread-attachments-title {
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .inline-att-list {
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                align-items: stretch;
                gap: var(--space-2);
            }
            .inline-att-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: var(--mail-attachment-tile, 200px);
                flex: 0 0 var(--mail-attachment-tile, 200px);
                min-width: 0;
                max-width: 100%;
                min-height: 56px;
                box-sizing: border-box;
                padding: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
            }
            .inline-att-row > platform-icon {
                flex-shrink: 0;
            }
            .inline-att-meta {
                flex: 1 1 auto;
                min-width: 0;
                max-width: none;
            }
            .inline-att-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .inline-att-size {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .inline-att-unavailable {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .reply-bar {
                margin-top: auto;
                border-top: 1px solid var(--border-subtle);
                padding: var(--space-3) var(--space-5);
                padding-bottom: max(var(--space-3), env(safe-area-inset-bottom, 0px));
                display: flex;
                align-items: center;
                gap: var(--space-3);
                background: var(--bg-surface);
                flex-wrap: wrap;
                flex-shrink: 0;
            }
            .reply-bar-input {
                flex: 1 1 12rem;
                min-width: 0;
                height: 2.25rem;
                padding: 0 var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-full, 999px);
                background: var(--bg-elevated);
                color: var(--text-primary);
                font: inherit;
                font-size: 0.875rem;
                outline: none;
            }
            .reply-bar-input::placeholder {
                color: var(--text-tertiary);
            }
            .reply-bar-input:focus {
                border-color: color-mix(in srgb, var(--accent) 55%, var(--border-subtle));
                box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent);
            }
            .reply-bar .thread-actions {
                flex-shrink: 0;
                margin-left: auto;
            }
            .compose {
                position: fixed;
                z-index: 40;
                margin: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-elevated);
                box-shadow: var(--glass-shadow-medium);
                display: flex;
                flex-direction: column;
                min-width: 320px;
                min-height: 280px;
                overflow: hidden;
                box-sizing: border-box;
            }
            .compose[data-expanded='true'] {
                border-radius: var(--radius-xl);
            }
            .compose[data-expanded='true'] .compose-header {
                cursor: default;
            }
            .compose[data-dragging='true'] {
                cursor: grabbing;
                user-select: none;
            }
            .compose[data-dragging='true'] .compose-header {
                cursor: grabbing;
            }
            .compose-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--bg-surface) 70%, transparent);
                flex-shrink: 0;
                cursor: grab;
                touch-action: none;
            }
            .compose platform-markdown-editor {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                border: none;
                border-radius: 0;
                --markdown-editor-min-height: 0;
                --markdown-editor-body-min-height: 0;
            }
            .compose-header-actions {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                flex-shrink: 0;
            }
            .compose-title {
                min-width: 0;
                font-size: 0.8125rem;
                font-weight: 650;
                color: var(--text-secondary);
                letter-spacing: 0.02em;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .compose-resize-handle {
                position: absolute;
                right: 0;
                bottom: 0;
                width: 18px;
                height: 18px;
                cursor: nwse-resize;
                touch-action: none;
                z-index: 2;
            }
            .compose-resize-handle::before {
                content: '';
                position: absolute;
                right: 4px;
                bottom: 4px;
                width: 10px;
                height: 10px;
                border-right: 2px solid color-mix(in srgb, var(--text-tertiary) 70%, transparent);
                border-bottom: 2px solid color-mix(in srgb, var(--text-tertiary) 70%, transparent);
                border-radius: 0 0 2px 0;
            }
            .compose[data-expanded='true'] .compose-resize-handle {
                display: none;
            }
            .compose-meta {
                display: flex;
                flex-direction: column;
                flex-shrink: 0;
            }
            .compose-row {
                display: grid;
                grid-template-columns: 72px minmax(0, 1fr);
                align-items: center;
                gap: var(--space-2);
                min-height: 40px;
                padding: 0 var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            .compose-row-label {
                font-size: 0.75rem;
                font-weight: 600;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .compose-input {
                width: 100%;
                min-width: 0;
                height: 36px;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font: inherit;
                font-size: 0.875rem;
                padding: 0;
            }
            .compose-input:focus {
                outline: none;
            }
            .compose-body {
                width: 100%;
                min-height: var(--mail-compose-min-height);
                flex: 1;
                resize: none;
                border: none;
                border-radius: 0;
                padding: var(--space-3) var(--space-4);
                background: transparent;
                color: var(--text-primary);
                font: inherit;
                font-size: 0.9375rem;
                line-height: 1.5;
            }
            .compose-body:focus {
                outline: none;
                box-shadow: none;
                border-color: transparent;
            }
            .compose-toolbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                border-top: 1px solid var(--border-subtle);
                background: var(--bg-surface);
            }
            .compose-toolbar-end {
                display: flex;
                gap: var(--space-2);
                align-items: center;
            }
            .empty {
                padding: var(--space-8, 48px) var(--space-6);
                color: var(--text-tertiary);
                text-align: center;
            }
            .empty-thread {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                height: 100%;
                min-height: 240px;
                padding: var(--space-8);
                color: var(--text-tertiary);
                text-align: center;
            }
            .empty-thread-title {
                font-size: 1.125rem;
                font-weight: 650;
                color: var(--text-secondary);
            }
            .empty-nav {
                padding: var(--space-3);
                text-align: left;
            }
            .shortcuts-hint {
                font-size: 0.75rem;
                color: var(--text-tertiary);
            }
            .settings-overlay {
                position: absolute;
                inset: 0;
                background: var(--bg-surface);
                z-index: 5;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .settings-panel {
                width: 100%;
                height: 100%;
                min-height: 0;
                background: var(--bg-surface);
                border: none;
                border-radius: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                gap: 0;
                box-shadow: none;
                overflow: hidden;
            }
            .settings-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-4) var(--space-6);
                border-bottom: 1px solid var(--border-subtle);
                flex-shrink: 0;
                background: var(--bg-elevated);
                z-index: 1;
            }
            .settings-header-title {
                font-weight: 700;
                font-size: 1.15rem;
            }
            .settings-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-6);
                padding: var(--space-5) var(--space-6) var(--space-8);
                overflow: auto;
                min-height: 0;
                flex: 1;
                max-width: 960px;
                width: 100%;
                margin: 0 auto;
                box-sizing: border-box;
            }
            .settings-hint {
                font-size: 0.85rem;
                color: var(--text-secondary);
                line-height: 1.45;
                max-width: 62ch;
            }
            .settings-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .settings-section-title {
                font-weight: 700;
                font-size: 0.95rem;
                letter-spacing: 0.01em;
            }
            .settings-row {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-elevated);
            }
            .settings-row-main {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                align-items: stretch;
            }
            .settings-row-meta {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                min-width: 0;
            }
            .settings-row-form {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                gap: var(--space-2) var(--space-3);
                align-items: end;
            }
            .settings-row-form > .settings-hint {
                grid-column: 1 / -1;
            }
            .settings-members {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding-top: var(--space-2);
                border-top: 1px solid var(--border-subtle);
            }
            .settings-member-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .binding-email {
                font-weight: 600;
                word-break: break-all;
                font-size: 0.95rem;
            }
            .binding-unassigned {
                font-size: 0.85rem;
                color: var(--text-tertiary);
            }
            .binding-color {
                width: 100%;
                min-width: 0;
            }
            .binding-actions {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                justify-content: flex-start;
                align-items: center;
            }
            .settings-create-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--bg-elevated) 70%, transparent);
            }
            .btn-icon {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .btn-icon:hover {
                background: var(--bg-hover);
                color: var(--text-primary);
            }
            .header-actions {
                display: flex;
                gap: var(--space-2);
                align-items: center;
            }
            platform-button.nav-compose {
                width: 100%;
                display: block;
            }
            @media (max-width: 767px) {
                /* Как calendar: rail слева + контент; folders-nav скрыт. */
                .mail-shell {
                    grid-template-columns: var(--mail-rail-width, 64px) minmax(0, 1fr);
                }
                .mail-nav {
                    display: none !important;
                }
                .mail-list,
                .mail-thread {
                    width: auto;
                    min-width: 0;
                    border-right: none;
                }
                .thread-back {
                    display: inline-flex;
                }
                .shortcuts-hint,
                .reply-bar {
                    display: none;
                }
                .chat-bubble-row {
                    max-width: 92%;
                }
                .mail-shell[data-pane='list'] .mail-thread,
                .mail-shell[data-pane='thread'] .mail-list,
                .mail-shell[data-pane='nav'] .mail-list,
                .mail-shell[data-pane='nav'] .mail-thread {
                    display: none;
                }
                .compose,
                .compose[data-expanded='true'] {
                    inset: 0 !important;
                    left: 0 !important;
                    top: 0 !important;
                    width: 100vw !important;
                    height: 100dvh !important;
                    max-width: 100vw !important;
                    max-height: 100dvh !important;
                    border-radius: 0 !important;
                    min-width: 0;
                    min-height: 0;
                }
                .compose-header {
                    cursor: default;
                    touch-action: auto;
                    padding-top: max(var(--space-3), env(safe-area-inset-top, 0px));
                }
                .compose-resize-handle {
                    display: none !important;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this._isFullscreen = true;
        this.openSettings = false;
        this._mailSelect = this.select((s) => s.mail);
        this._calendarSelect = this.select((s) => s.calendar);
        this._authSelect = this.select((s) => s.auth);
        this._localeSelect = this.select((s) => s.i18n.locale);
        this._teamSelect = this.select((s) => s.team);
        this._adminDraft = null;
        this._createLocalPart = '';
        this._createUserId = '';
        this._assignDrafts = {};
        this._mobilePane = 'list';
        this._composeOpen = false;
        this._composeExpanded = false;
        this._composePos = null;
        this._composeSize = null;
        this._composeDragging = false;
        this._composeResizing = false;
        this._composeDragState = null;
        this._composeResizeState = null;
        this._listQuery = '';
        this._quickReplyText = '';
        this._expandedThreadIds = [];
        this._createKind = 'user';
        this._memberDraftUserId = '';
        this._searchDebounceTimer = null;
        this._draftSaveTimer = null;
        this._onMailKeydown = (event) => this._handleMailKeydown(event);
        this._boundComposePointerMove = (event) => this._onComposePointerMove(event);
        this._boundComposePointerUp = (event) => this._onComposePointerUp(event);
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(MAIL_EVENTS.BINDINGS_LOAD_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.MESSAGES_LOAD_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.MESSAGE_LOAD_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.THREAD_LOAD_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.MESSAGE_SEND_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.CONNECTION_SAVE_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.BINDING_CREATE_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.BINDING_PATCH_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.BINDING_DELETE_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.DEFAULT_SET_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.MESSAGE_TRASH_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.MESSAGE_ARCHIVE_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.MESSAGE_DELETE_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.MESSAGE_STAR_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.SYNC_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.DRAFT_SAVE_FAILED, (e) => this._toastErr(e));
        this.useEvent(MAIL_EVENTS.BINDING_CREATED, () => {
            this.toast('toast_binding_created', { type: 'success' });
        });
        this.useEvent(MAIL_EVENTS.COMPANY_BINDINGS_LOADED, () => {
            const mail = this._mailSelect.value;
            for (const binding of mail.companyBindings) {
                if (binding.kind === 'role') {
                    this._ensureRoleMembersLoaded(binding.mailbox_binding_id);
                }
            }
        });
        this.useEvent(MAIL_EVENTS.BINDING_DELETED, () => {
            this.toast('toast_binding_deleted', { type: 'success' });
        });
        this.useEvent(MAIL_EVENTS.DEFAULT_SET, () => {
            this.toast('toast_default_set', { type: 'success' });
        });
        this.useEvent(MAIL_EVENTS.MESSAGE_SENT, () => {
            this._closeCompose();
            this.toast('toast_sent', { type: 'success' });
        });
        window.addEventListener('keydown', this._onMailKeydown);
    }

    disconnectedCallback() {
        window.removeEventListener('keydown', this._onMailKeydown);
        this._endComposePointerSession();
        super.disconnectedCallback();
    }

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        this.title = this.t('title');
        if (changedProperties.has('open')) {
            if (this.open) {
                this._onModalOpened();
            } else {
                this._closeCompose();
                this._listQuery = '';
                this._expandedThreadIds = [];
            }
        }
    }

    _toastErr(event) {
        const message = event.payload && typeof event.payload.message === 'string'
            ? event.payload.message
            : '';
        this.toast('err_generic', { type: 'error', vars: { message } });
    }

    _onModalOpened() {
        this.size = 'full';
        this._isFullscreen = true;
        this._mobilePane = 'list';
        this._closeCompose();
        this._listQuery = '';
        this._expandedThreadIds = [];
        this.dispatch(MAIL_EVENTS.BOOTSTRAP_REQUESTED, null);
        this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        const now = new Date();
        const end = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
        this.dispatch(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {
            start_at: now.toISOString(),
            end_at: end.toISOString(),
            include_sources: null,
            limit: 50,
        });
        if (this.openSettings === true) {
            this._openSettings();
        }
    }

    _isCompanyAdmin() {
        const auth = this._authSelect.value;
        const companyId = auth.activeCompanyId;
        const raw = auth.user && auth.user.raw;
        if (!companyId || !raw || !raw.companies || typeof raw.companies !== 'object') {
            return false;
        }
        const roles = raw.companies[companyId];
        return Array.isArray(roles) && roles.includes('admin');
    }

    _activeBinding() {
        const mail = this._mailSelect.value;
        return mail.bindings.find((b) => b.mailbox_binding_id === mail.activeMailboxBindingId) || null;
    }

    _localeTag() {
        const locale = this._localeSelect.value;
        if (locale === 'ru' || locale === 'en') {
            return locale;
        }
        return 'en';
    }

    _selectMailbox(mailboxBindingId) {
        this.dispatch(MAIL_EVENTS.MAILBOX_SELECT, { mailbox_binding_id: mailboxBindingId });
        this._mobilePane = 'list';
        this._closeCompose();
        this._listQuery = '';
        this._expandedThreadIds = [];
    }

    _selectFolder(folder) {
        this.dispatch(MAIL_EVENTS.FOLDER_SELECT, { folder });
        this._mobilePane = 'list';
        this._closeCompose();
        this._listQuery = '';
        this._expandedThreadIds = [];
    }

    _composeMargin() {
        return 16;
    }

    _defaultComposeSize() {
        const margin = this._composeMargin();
        const width = Math.min(560, Math.max(320, window.innerWidth - margin * 2));
        const height = Math.min(520, Math.max(280, window.innerHeight - margin * 2));
        return { w: Math.round(width), h: Math.round(height) };
    }

    _defaultComposePos(size) {
        const margin = this._composeMargin();
        return {
            x: Math.max(margin, Math.round(window.innerWidth - size.w - margin)),
            y: Math.max(margin, Math.round(window.innerHeight - size.h - margin)),
        };
    }

    _resetComposeGeometry() {
        const size = this._defaultComposeSize();
        this._composeExpanded = false;
        this._composeSize = size;
        this._composePos = this._defaultComposePos(size);
    }

    _showComposePanel() {
        this._resetComposeGeometry();
        if (window.innerWidth <= 767) {
            this._composeExpanded = true;
        }
        this._composeOpen = true;
        this._mobilePane = 'thread';
    }

    _composePanelStyle() {
        if (!this._composeOpen) {
            return '';
        }
        if (this._composeExpanded) {
            const margin = this._composeMargin();
            return `left:${margin}px;top:${margin}px;width:calc(100vw - ${margin * 2}px);height:calc(100dvh - ${margin * 2}px);`;
        }
        const size = this._composeSize || this._defaultComposeSize();
        const pos = this._composePos || this._defaultComposePos(size);
        return `left:${pos.x}px;top:${pos.y}px;width:${size.w}px;height:${size.h}px;`;
    }

    _composeEventOnInteractive(event) {
        for (const node of event.composedPath()) {
            if (node === this.shadowRoot || node === this) {
                break;
            }
            if (node instanceof HTMLElement) {
                const tag = node.tagName;
                if (
                    tag === 'BUTTON'
                    || tag === 'INPUT'
                    || tag === 'TEXTAREA'
                    || tag === 'SELECT'
                    || tag === 'A'
                    || node.getAttribute('role') === 'button'
                ) {
                    return true;
                }
            }
        }
        return false;
    }

    _clampComposePos(x, y, width, height) {
        const margin = this._composeMargin();
        const maxX = Math.max(margin, window.innerWidth - width - margin);
        const maxY = Math.max(margin, window.innerHeight - height - margin);
        return {
            x: Math.min(maxX, Math.max(margin, Math.round(x))),
            y: Math.min(maxY, Math.max(margin, Math.round(y))),
        };
    }

    _clampComposeSize(width, height, left, top) {
        const margin = this._composeMargin();
        const maxW = Math.max(320, window.innerWidth - left - margin);
        const maxH = Math.max(280, window.innerHeight - top - margin);
        return {
            w: Math.min(maxW, Math.max(320, Math.round(width))),
            h: Math.min(maxH, Math.max(280, Math.round(height))),
        };
    }

    _endComposePointerSession() {
        this._composeDragging = false;
        this._composeResizing = false;
        this._composeDragState = null;
        this._composeResizeState = null;
        window.removeEventListener('pointermove', this._boundComposePointerMove);
        window.removeEventListener('pointerup', this._boundComposePointerUp);
        window.removeEventListener('pointercancel', this._boundComposePointerUp);
    }

    _onComposeHeaderPointerDown(event) {
        if (this._composeExpanded || event.button !== 0 || this._composeEventOnInteractive(event)) {
            return;
        }
        const size = this._composeSize || this._defaultComposeSize();
        const pos = this._composePos || this._defaultComposePos(size);
        this._composeDragging = true;
        this._composeDragState = {
            pointerId: event.pointerId,
            offsetX: event.clientX - pos.x,
            offsetY: event.clientY - pos.y,
            width: size.w,
            height: size.h,
        };
        window.addEventListener('pointermove', this._boundComposePointerMove);
        window.addEventListener('pointerup', this._boundComposePointerUp);
        window.addEventListener('pointercancel', this._boundComposePointerUp);
        event.preventDefault();
    }

    _onComposeResizePointerDown(event) {
        if (this._composeExpanded || event.button !== 0) {
            return;
        }
        const size = this._composeSize || this._defaultComposeSize();
        const pos = this._composePos || this._defaultComposePos(size);
        this._composeResizing = true;
        this._composeResizeState = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            startW: size.w,
            startH: size.h,
            left: pos.x,
            top: pos.y,
        };
        window.addEventListener('pointermove', this._boundComposePointerMove);
        window.addEventListener('pointerup', this._boundComposePointerUp);
        window.addEventListener('pointercancel', this._boundComposePointerUp);
        event.preventDefault();
        event.stopPropagation();
    }

    _onComposePointerMove(event) {
        if (this._composeDragging && this._composeDragState
            && event.pointerId === this._composeDragState.pointerId) {
            const next = this._clampComposePos(
                event.clientX - this._composeDragState.offsetX,
                event.clientY - this._composeDragState.offsetY,
                this._composeDragState.width,
                this._composeDragState.height,
            );
            this._composePos = next;
            return;
        }
        if (this._composeResizing && this._composeResizeState
            && event.pointerId === this._composeResizeState.pointerId) {
            const state = this._composeResizeState;
            const nextSize = this._clampComposeSize(
                state.startW + (event.clientX - state.startX),
                state.startH + (event.clientY - state.startY),
                state.left,
                state.top,
            );
            this._composeSize = nextSize;
            this._composePos = { x: state.left, y: state.top };
        }
    }

    _onComposePointerUp(event) {
        const drag = this._composeDragState;
        const resize = this._composeResizeState;
        if (drag && event.pointerId === drag.pointerId) {
            this._endComposePointerSession();
            return;
        }
        if (resize && event.pointerId === resize.pointerId) {
            this._endComposePointerSession();
        }
    }

    _toggleComposeExpanded() {
        if (!this._composeOpen) {
            throw new Error('platform-mail-modal: compose is closed');
        }
        this._endComposePointerSession();
        if (this._composeExpanded) {
            this._composeExpanded = false;
            if (!this._composeSize || !this._composePos) {
                const size = this._defaultComposeSize();
                this._composeSize = size;
                this._composePos = this._defaultComposePos(size);
            }
            return;
        }
        this._composeExpanded = true;
    }

    _folderLabel(folder) {
        const meta = FOLDER_ROLE_META[folder.role];
        if (meta) return this.t(meta.key);
        return folder.name;
    }

    _folderIcon(folder) {
        const meta = FOLDER_ROLE_META[folder.role];
        if (meta) return meta.icon;
        return 'mail';
    }

    _ensureStandardFolders() {
        const mail = this._mailSelect.value;
        if (!mail.activeMailboxBindingId) return;
        this.dispatch(MAIL_EVENTS.FOLDERS_ENSURE_REQUESTED, {
            mailbox_binding_id: mail.activeMailboxBindingId,
        });
    }

    _ownEmails() {
        return new Set(this._mailSelect.value.bindings.map((b) => b.email_address.toLowerCase()));
    }

    _startCompose() {
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, {
            to: '',
            subject: '',
            body: '',
            body_html: '',
            attachments: [],
            in_reply_to: null,
            references: null,
        });
        this._showComposePanel();
    }

    _replyTargetMessage(mail) {
        const items = mail.selectedThreadMessages;
        if (Array.isArray(items) && items.length > 0) {
            return items[items.length - 1];
        }
        return mail.selectedMessage;
    }

    _activeMailboxEmail() {
        const active = this._activeBinding();
        if (!active || typeof active.email_address !== 'string') {
            return '';
        }
        return active.email_address.toLowerCase();
    }

    _isMineAddress(fromAddress) {
        const mine = this._activeMailboxEmail();
        if (!mine) return false;
        const parsed = parseMailAddress(fromAddress);
        return parsed.email.length > 0 && parsed.email.toLowerCase() === mine;
    }

    _sentFolderName(mail) {
        const folders = Array.isArray(mail.folders) ? mail.folders : [];
        const sent = folders.find((folder) => folder && folder.role === 'sent');
        return sent && typeof sent.name === 'string' ? sent.name : '';
    }

    _isMineMessage(message, mail) {
        if (this._isMineAddress(message.from_address)) {
            return true;
        }
        const sentName = this._sentFolderName(mail);
        return sentName.length > 0
            && typeof message.folder === 'string'
            && message.folder === sentName;
    }

    _previewItemsForThread(thread, mail) {
        if (
            mail.selectedThreadId === thread.threadId
            && Array.isArray(mail.selectedThreadMessages)
            && mail.selectedThreadMessages.length > 0
        ) {
            return mail.selectedThreadMessages;
        }
        return thread.messages;
    }

    _replyDraftPayload(message, overrides = {}) {
        const from = parseMailAddress(message.from_address);
        const subject = typeof message.subject === 'string' ? message.subject : '';
        const references = [
            ...(typeof message.references === 'string' && message.references.trim()
                ? message.references.trim().split(/\s+/)
                : []),
            ...(typeof message.message_id === 'string' && message.message_id.trim()
                ? [message.message_id.trim()]
                : []),
        ].filter((item, index, arr) => item && arr.indexOf(item) === index).join(' ');
        return {
            to: from.email,
            subject: subjectWithPrefix(subject, 'Re:'),
            body: '',
            body_html: '',
            attachments: [],
            in_reply_to: message.message_id,
            references: references || message.message_id,
            ...overrides,
        };
    }

    _openReply() {
        const message = this._replyTargetMessage(this._mailSelect.value);
        if (!message) {
            this._startCompose();
            return;
        }
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, this._replyDraftPayload(message));
        this._showComposePanel();
    }

    _focusQuickReplyInput() {
        const root = this.renderRoot;
        if (!root) {
            return;
        }
        const input = root.querySelector('.reply-bar-input');
        if (input instanceof HTMLInputElement) {
            input.focus();
        }
    }

    _onQuickReplyInput(event) {
        const value = event.target && typeof event.target.value === 'string'
            ? event.target.value
            : '';
        this._quickReplyText = value;
    }

    _onQuickReplyKeydown(event) {
        if (event.key !== 'Enter' || event.shiftKey) {
            return;
        }
        event.preventDefault();
        this._submitQuickReply();
    }

    _submitQuickReply() {
        const text = this._quickReplyText.trim();
        if (!text) {
            this._openReply();
            return;
        }
        const message = this._replyTargetMessage(this._mailSelect.value);
        if (!message) {
            this._startCompose();
            return;
        }
        const escaped = escapeHtml(text).replace(/\n/g, '<br>');
        this.dispatch(
            MAIL_EVENTS.COMPOSE_DRAFT_SET,
            this._replyDraftPayload(message, {
                body: text,
                body_html: sanitizeMarkdownEditorHtml(`<p>${escaped}</p>`),
            }),
        );
        this._quickReplyText = '';
        this._sendReply();
    }

    _openReplyAll() {
        const message = this._replyTargetMessage(this._mailSelect.value);
        if (!message) {
            this._startCompose();
            return;
        }
        this._openReplyAllForMessage(message);
    }

    _openReplyAllForMessage(message) {
        if (!message) {
            throw new Error('platform-mail-modal: message required for reply-all');
        }
        const own = this._ownEmails();
        const from = parseMailAddress(message.from_address);
        const recipients = [];
        if (from.email && !own.has(from.email.toLowerCase())) {
            recipients.push(from.email);
        }
        const toAddresses = Array.isArray(message.to_addresses) ? message.to_addresses : [];
        for (const addr of toAddresses) {
            const parsed = parseMailAddress(addr);
            if (parsed.email && !own.has(parsed.email.toLowerCase()) && !recipients.includes(parsed.email)) {
                recipients.push(parsed.email);
            }
        }
        const subject = typeof message.subject === 'string' ? message.subject : '';
        const references = [
            ...(typeof message.references === 'string' && message.references.trim()
                ? message.references.trim().split(/\s+/)
                : []),
            ...(typeof message.message_id === 'string' && message.message_id.trim()
                ? [message.message_id.trim()]
                : []),
        ].filter((item, index, arr) => item && arr.indexOf(item) === index).join(' ');
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, {
            to: recipients.join(', '),
            subject: subjectWithPrefix(subject, 'Re:'),
            body: '',
            body_html: '',
            attachments: [],
            in_reply_to: message.message_id,
            references: references || message.message_id,
        });
        this._showComposePanel();
    }

    _openForward() {
        const message = this._replyTargetMessage(this._mailSelect.value);
        if (!message) {
            this._startCompose();
            return;
        }
        const subject = typeof message.subject === 'string' ? message.subject : '';
        const bodyText = typeof message.body_text === 'string' ? message.body_text : '';
        const from = typeof message.from_address === 'string' ? message.from_address : '';
        const quoted = [
            '',
            '---------- Forwarded message ----------',
            from ? `From: ${from}` : '',
            subject ? `Subject: ${subject}` : '',
            '',
            bodyText,
        ].filter((line, idx, arr) => !(line === '' && idx > 0 && arr[idx - 1] === '')).join('\n');
        const quotedHtml = sanitizeMarkdownEditorHtml(
            `<p></p><p>---------- Forwarded message ----------</p>${from ? `<p>From: ${from}</p>` : ''}${subject ? `<p>Subject: ${subject}</p>` : ''}<p></p><pre>${bodyText.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>`,
        );
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, {
            to: '',
            subject: subjectWithPrefix(subject, 'Fwd:'),
            body: quoted,
            body_html: quotedHtml,
            attachments: [],
            in_reply_to: null,
            references: null,
        });
        this._showComposePanel();
    }

    _closeCompose() {
        this._endComposePointerSession();
        this._composeOpen = false;
        this._composeExpanded = false;
        this._composePos = null;
        this._composeSize = null;
    }

    _filteredMessages(mail) {
        return Array.isArray(mail.messages) ? mail.messages : [];
    }

    _filteredThreads(mail) {
        return groupMailThreads(this._filteredMessages(mail));
    }

    _onListSearchInput(event) {
        const value = event.target && typeof event.target.value === 'string'
            ? event.target.value
            : '';
        this._listQuery = value;
        if (this._searchDebounceTimer != null) {
            clearTimeout(this._searchDebounceTimer);
        }
        this._searchDebounceTimer = setTimeout(() => {
            this._searchDebounceTimer = null;
            this._runServerSearch();
        }, 300);
    }

    _runServerSearch() {
        const mail = this._mailSelect.value;
        if (!mail.activeMailboxBindingId || !mail.folder) return;
        const q = this._listQuery.trim();
        if (!q) {
            this.dispatch(MAIL_EVENTS.MESSAGES_LOAD_REQUESTED, {
                mailbox_binding_id: mail.activeMailboxBindingId,
                folder: mail.folder,
            });
            return;
        }
        this.dispatch(MAIL_EVENTS.MESSAGES_SEARCH_REQUESTED, {
            mailbox_binding_id: mail.activeMailboxBindingId,
            folder: mail.folder,
            q,
        });
    }

    _loadMoreMessages() {
        const mail = this._mailSelect.value;
        if (!mail.activeMailboxBindingId || !mail.folder || !mail.messagesNextCursor) return;
        this.dispatch(MAIL_EVENTS.MESSAGES_LOAD_MORE_REQUESTED, {
            mailbox_binding_id: mail.activeMailboxBindingId,
            folder: mail.folder,
            cursor: mail.messagesNextCursor,
        });
    }

    _selectedActionPayload() {
        const mail = this._mailSelect.value;
        const uid = mail.selectedUid;
        if (typeof uid !== 'string' || uid.length === 0) return null;
        if (!mail.activeMailboxBindingId || !mail.folder) return null;
        return {
            mailbox_binding_id: mail.activeMailboxBindingId,
            folder: mail.folder,
            uid,
        };
    }

    _trashSelected() {
        const payload = this._selectedActionPayload();
        if (!payload) return;
        this.dispatch(MAIL_EVENTS.MESSAGE_TRASH_REQUESTED, payload);
        this._mobilePane = 'list';
    }

    _archiveSelected() {
        const payload = this._selectedActionPayload();
        if (!payload) return;
        this.dispatch(MAIL_EVENTS.MESSAGE_ARCHIVE_REQUESTED, payload);
        this._mobilePane = 'list';
    }

    _deleteSelectedForever() {
        const payload = this._selectedActionPayload();
        if (!payload) return;
        this.dispatch(MAIL_EVENTS.MESSAGE_DELETE_REQUESTED, payload);
        this._mobilePane = 'list';
    }

    _toggleStarSelected() {
        const mail = this._mailSelect.value;
        const payload = this._selectedActionPayload();
        if (!payload) return;
        const current = mail.selectedMessage && mail.selectedMessage.flagged === true;
        const listItem = mail.messages.find((item) => item.uid === payload.uid);
        const flagged = !(current || (listItem && listItem.flagged === true));
        this.dispatch(MAIL_EVENTS.MESSAGE_STAR_REQUESTED, { ...payload, flagged });
    }

    _scheduleDraftSave() {
        const mail = this._mailSelect.value;
        if (!mail.activeMailboxBindingId || !this._composeOpen) return;
        if (this._draftSaveTimer != null) {
            clearTimeout(this._draftSaveTimer);
        }
        this._draftSaveTimer = setTimeout(() => {
            this._draftSaveTimer = null;
            this._saveDraftNow();
        }, 800);
    }

    _saveDraftNow() {
        const mail = this._mailSelect.value;
        if (!mail.activeMailboxBindingId) return;
        const toAddresses = parseToList(mail.compose.to);
        this.dispatch(MAIL_EVENTS.DRAFT_SAVE_REQUESTED, {
            mailbox_binding_id: mail.activeMailboxBindingId,
            subject: mail.compose.subject,
            body_text: mail.compose.body,
            body_html: typeof mail.compose.body_html === 'string' && mail.compose.body_html.trim()
                ? mail.compose.body_html
                : null,
            to_addresses: toAddresses,
            uid: mail.draftUid,
            in_reply_to: mail.compose.in_reply_to,
            references: mail.compose.references,
        });
    }

    _openDraftFromMessage(message) {
        if (!message) return;
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, {
            to: Array.isArray(message.to_addresses) ? message.to_addresses.join(', ') : '',
            subject: typeof message.subject === 'string' ? message.subject : '',
            body: typeof message.body_text === 'string' ? message.body_text : '',
            body_html: typeof message.body_html === 'string' ? message.body_html : '',
            in_reply_to: message.in_reply_to || null,
            references: message.references || null,
            attachments: [],
        });
        this._showComposePanel();
    }

    _toggleThreadExpand(thread, event) {
        event.preventDefault();
        event.stopPropagation();
        if (!thread || typeof thread.threadId !== 'string' || !thread.latest) {
            throw new Error('platform-mail-modal: thread required for expand');
        }
        const threadId = thread.threadId;
        const current = Array.isArray(this._expandedThreadIds) ? this._expandedThreadIds : [];
        if (current.includes(threadId)) {
            this._expandedThreadIds = current.filter((id) => id !== threadId);
            return;
        }
        this._expandedThreadIds = [...current, threadId];
        // Полный тред = INBOX + Sent; в list-папке своих ответов нет.
        this.dispatch(MAIL_EVENTS.THREAD_SELECT, {
            uid: thread.latest.uid,
            thread_id: threadId,
        });
    }

    _selectThread(thread) {
        if (!thread || typeof thread.threadId !== 'string' || !thread.latest) {
            throw new Error('platform-mail-modal: thread required');
        }
        this._closeCompose();
        this._quickReplyText = '';
        const mail = this._mailSelect.value;
        const folderMeta = mail.folders.find((folder) => folder.name === mail.folder);
        if (folderMeta && folderMeta.role === 'drafts') {
            this._openDraftFromMessage(thread.latest);
            this.dispatch(MAIL_EVENTS.THREAD_SELECT, {
                uid: thread.latest.uid,
                thread_id: thread.threadId,
            });
            this._mobilePane = 'thread';
            return;
        }
        this.dispatch(MAIL_EVENTS.THREAD_SELECT, {
            uid: thread.latest.uid,
            thread_id: thread.threadId,
        });
        this._mobilePane = 'thread';
    }

    _selectAdjacentMessage(delta) {
        const mail = this._mailSelect.value;
        const threads = this._filteredThreads(mail);
        if (threads.length === 0) return;
        const current = findThreadByUid(threads, mail.selectedUid);
        const currentIdx = current
            ? threads.findIndex((thread) => thread.threadId === current.threadId)
            : -1;
        let nextIdx = currentIdx + delta;
        if (currentIdx < 0) nextIdx = delta > 0 ? 0 : threads.length - 1;
        if (nextIdx < 0 || nextIdx >= threads.length) return;
        this._selectThread(threads[nextIdx]);
    }

    _deepActiveElement() {
        let element = document.activeElement;
        while (element instanceof Element && element.shadowRoot && element.shadowRoot.activeElement) {
            element = element.shadowRoot.activeElement;
        }
        return element;
    }

    _isEditableElement(node) {
        if (!(node instanceof Element)) return false;
        const tag = node.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
        if (node.isContentEditable) return true;
        if (node.classList.contains('list-search')) return true;
        if (node.closest('platform-markdown-editor')) return true;
        return Boolean(node.closest('platform-field'));
    }

    _isTypingTarget(event) {
        // window keydown + shadow DOM: event.target ретаргетится на host,
        // реальный input — в composedPath / deep activeElement.
        const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
        for (const node of path) {
            if (this._isEditableElement(node)) return true;
        }
        return this._isEditableElement(this._deepActiveElement());
    }

    _handleMailKeydown(event) {
        if (!this.open || this._mailSelect.value.adminMode) return;
        if (this._isTypingTarget(event)) return;
        const key = event.key;
        if (key === 'Escape') {
            if (this._composeOpen) {
                event.preventDefault();
                this._closeCompose();
                return;
            }
            return;
        }
        if (key === 'j' || key === 'J') {
            event.preventDefault();
            this._selectAdjacentMessage(1);
            return;
        }
        if (key === 'k' || key === 'K') {
            event.preventDefault();
            this._selectAdjacentMessage(-1);
            return;
        }
        if (key === 'c' || key === 'C') {
            event.preventDefault();
            this._startCompose();
            return;
        }
        if (key === 'r' || key === 'R') {
            event.preventDefault();
            if (this._quickReplyText.trim().length > 0) {
                this._submitQuickReply();
                return;
            }
            this._focusQuickReplyInput();
            return;
        }
        if (key === 'f' || key === 'F') {
            event.preventDefault();
            this._openForward();
            return;
        }
        if (key === 'u' || key === 'U') {
            event.preventDefault();
            this._markSelectedUnseen();
            return;
        }
        if (key === 'e' || key === 'E') {
            event.preventDefault();
            this._archiveSelected();
            return;
        }
        if (key === '#' || key === 'Delete' || key === 'Backspace') {
            event.preventDefault();
            this._trashSelected();
            return;
        }
        if (key === 's' || key === 'S') {
            event.preventDefault();
            this._toggleStarSelected();
        }
    }

    _refreshMessages() {
        const mail = this._mailSelect.value;
        if (!mail.activeMailboxBindingId || !mail.folder) return;
        this.dispatch(MAIL_EVENTS.SYNC_REQUESTED, {
            mailbox_binding_id: mail.activeMailboxBindingId,
        });
        this.dispatch(MAIL_EVENTS.MESSAGES_LOAD_REQUESTED, {
            mailbox_binding_id: mail.activeMailboxBindingId,
            folder: mail.folder,
        });
    }

    _markSelectedUnseen() {
        const mail = this._mailSelect.value;
        const uid = mail.selectedUid;
        if (typeof uid !== 'string' || uid.length === 0) return;
        if (!mail.activeMailboxBindingId || !mail.folder) return;
        this.dispatch(MAIL_EVENTS.MESSAGE_MARK_UNSEEN_REQUESTED, {
            uid,
            mailbox_binding_id: mail.activeMailboxBindingId,
            folder: mail.folder,
        });
    }

    _selectMessage(uid) {
        const mail = this._mailSelect.value;
        const threads = groupMailThreads(mail.messages);
        const thread = findThreadByUid(threads, uid);
        if (thread) {
            this._selectThread(thread);
            return;
        }
        this._closeCompose();
        this.dispatch(MAIL_EVENTS.THREAD_SELECT, { uid, thread_id: null });
        this._mobilePane = 'thread';
    }

    _openSettings() {
        const connection = this._mailSelect.value.connection;
        this._adminDraft = connection
            ? {
                mail_domain: connection.mail_domain,
                provider: connection.provider,
                imap_host: connection.imap_host,
                imap_port: connection.imap_port,
                smtp_host: connection.smtp_host,
                smtp_port: connection.smtp_port,
                use_ssl: connection.use_ssl,
            }
            : {
                mail_domain: '',
                provider: 'ispmanager',
                imap_host: '',
                imap_port: 993,
                smtp_host: '',
                smtp_port: 465,
                use_ssl: true,
            };
        this.dispatch(MAIL_EVENTS.ADMIN_MODE_SET, { open: true });
        if (this._isCompanyAdmin()) {
            this.dispatch(MAIL_EVENTS.COMPANY_BINDINGS_LOAD_REQUESTED, null);
            this.dispatch(MAIL_EVENTS.CONNECTION_LOAD_REQUESTED, null);
        }
    }

    _patchBindingColor(mailboxBindingId, pickerValue) {
        const calendarColor = paletteKeyFromPickerValue(pickerValue);
        this.dispatch(MAIL_EVENTS.BINDING_PATCH_REQUESTED, {
            mailbox_binding_id: mailboxBindingId,
            calendar_color: calendarColor,
        });
    }

    _closeSettings() {
        this.dispatch(MAIL_EVENTS.ADMIN_MODE_SET, { open: false });
        this._adminDraft = null;
        this._assignDrafts = {};
        this._createLocalPart = '';
        this._createUserId = '';
    }

    _saveConnection() {
        if (!this._adminDraft) return;
        this.dispatch(MAIL_EVENTS.CONNECTION_SAVE_REQUESTED, {
            mail_domain: this._adminDraft.mail_domain,
            provider: this._adminDraft.provider,
            imap_host: this._adminDraft.imap_host,
            imap_port: Number(this._adminDraft.imap_port),
            smtp_host: this._adminDraft.smtp_host,
            smtp_port: Number(this._adminDraft.smtp_port),
            use_ssl: Boolean(this._adminDraft.use_ssl),
            status: 'active',
        });
    }

    _memberOptions() {
        return this._teamSelect.value.members.map((m) => ({
            value: m.user_id,
            label: m.name || m.user_id,
        }));
    }

    _assignDraftFor(binding) {
        const draft = this._assignDrafts[binding.mailbox_binding_id];
        if (typeof draft === 'string' && draft.length > 0) return draft;
        if (typeof binding.user_id === 'string' && binding.user_id.length > 0) {
            return binding.user_id;
        }
        return '';
    }

    _setAssignDraft(mailboxBindingId, userId) {
        this._assignDrafts = {
            ...this._assignDrafts,
            [mailboxBindingId]: userId,
        };
    }

    _createBinding() {
        const localPart = this._createLocalPart.trim().toLowerCase();
        const kind = this._createKind === 'role' ? 'role' : 'user';
        if (!localPart) {
            this.toast('create_binding_required', { type: 'warning' });
            return;
        }
        if (kind === 'user') {
            const userId = this._createUserId.trim();
            if (!userId) {
                this.toast('create_binding_required', { type: 'warning' });
                return;
            }
            this.dispatch(MAIL_EVENTS.BINDING_CREATE_REQUESTED, {
                kind: 'user',
                user_id: userId,
                local_part: localPart,
                provision: true,
                sync_enabled: true,
            });
        } else {
            this.dispatch(MAIL_EVENTS.BINDING_CREATE_REQUESTED, {
                kind: 'role',
                user_id: null,
                local_part: localPart,
                provision: true,
                sync_enabled: true,
            });
        }
        this._createLocalPart = '';
        this._createUserId = '';
        this._createKind = 'user';
    }

    _assignCompanyBinding(binding) {
        const userId = this._assignDraftFor(binding).trim();
        if (!userId) {
            this.toast('assign_user_required', { type: 'warning' });
            return;
        }
        if (binding.user_id === userId && binding.kind === 'user') {
            return;
        }
        this.dispatch(MAIL_EVENTS.BINDING_CREATE_REQUESTED, {
            kind: 'user',
            user_id: userId,
            local_part: binding.local_part,
            provision: true,
            sync_enabled: true,
        });
    }

    async _confirmUnbind(binding) {
        const ok = await platformConfirm(
            this.t('unbind_confirm_message', { email: binding.email_address }),
            {
                title: this.t('unbind_confirm_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('unbind_confirm'),
                cancelText: this.t('unbind_cancel'),
            },
        );
        if (!ok) return;
        this.dispatch(MAIL_EVENTS.BINDING_DELETE_REQUESTED, {
            mailbox_binding_id: binding.mailbox_binding_id,
        });
    }

    _sendReply() {
        const mail = this._mailSelect.value;
        if (!mail.activeMailboxBindingId) return;
        const toAddresses = parseToList(mail.compose.to);
        if (toAddresses.length === 0) return;
        const attachments = Array.isArray(mail.compose.attachments)
            ? mail.compose.attachments.map((item) => ({
                filename: item.filename,
                content_type: item.content_type,
                content: item.content_base64,
            }))
            : [];
        const bodyHtml = typeof mail.compose.body_html === 'string' ? mail.compose.body_html.trim() : '';
        this.dispatch(MAIL_EVENTS.MESSAGE_SEND_REQUESTED, {
            mailbox_binding_id: mail.activeMailboxBindingId,
            to_addresses: toAddresses,
            subject: mail.compose.subject,
            body_text: mail.compose.body,
            body_html: bodyHtml.length > 0 ? bodyHtml : null,
            in_reply_to: mail.compose.in_reply_to,
            references: mail.compose.references,
            attachments,
        });
        this._closeCompose();
    }

    _onEditorChange(event) {
        const detail = event.detail;
        if (!detail || typeof detail !== 'object') {
            throw new Error('platform-mail-modal: editor change detail required');
        }
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, {
            body: typeof detail.textValue === 'string' ? detail.textValue : '',
            body_html: typeof detail.htmlValue === 'string' ? detail.htmlValue : '',
        });
        this._scheduleDraftSave();
    }

    _onEditorAttachmentsChange(event) {
        const detail = event.detail;
        if (!detail || !Array.isArray(detail.attachments)) {
            throw new Error('platform-mail-modal: attachments-change requires attachments[]');
        }
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, { attachments: detail.attachments });
    }

    _downloadAttachment(att) {
        if (!att || typeof att.content_base64 !== 'string' || att.content_base64.length === 0) {
            throw new Error('platform-mail-modal: attachment content_base64 required for download');
        }
        const binary = atob(att.content_base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: att.content_type || 'application/octet-stream' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = att.filename;
        anchor.click();
        URL.revokeObjectURL(url);
    }

    _attachmentFileRefs(attachments) {
        if (!Array.isArray(attachments)) {
            return [];
        }
        return attachments
            .filter((att) => att && typeof att.file_id === 'string' && att.file_id.length > 0)
            .map((att) => ({
                file_id: att.file_id,
                original_name: typeof att.filename === 'string' && att.filename.length > 0
                    ? att.filename
                    : att.file_id,
                content_type: typeof att.content_type === 'string' && att.content_type.length > 0
                    ? att.content_type
                    : 'application/octet-stream',
                file_size: typeof att.size === 'number' ? att.size : 0,
            }));
    }

    _attachmentsWithoutFileId(attachments) {
        if (!Array.isArray(attachments)) {
            return [];
        }
        return attachments.filter(
            (att) => !(att && typeof att.file_id === 'string' && att.file_id.length > 0),
        );
    }

    _renderInlineAttachmentRow(att) {
        const filename = typeof att.filename === 'string' && att.filename.length > 0
            ? att.filename
            : this.t('attachment_unnamed');
        const contentType = typeof att.content_type === 'string' ? att.content_type : '';
        const sizeLabel = typeof att.size === 'number' && att.size > 0
            ? formatFileSize(att.size)
            : '';
        const canDownload = typeof att.content_base64 === 'string' && att.content_base64.length > 0;
        return html`
            <div class="inline-att-row">
                <platform-icon
                    file-icon
                    name=${resolveFileIconKey(filename, contentType)}
                    size="32"
                ></platform-icon>
                <div class="inline-att-meta">
                    <div class="inline-att-name">${filename}</div>
                    ${sizeLabel.length > 0
                        ? html`<div class="inline-att-size">${sizeLabel}</div>`
                        : nothing}
                    ${!canDownload
                        ? html`<div class="inline-att-unavailable">${this.t('attachment_unavailable')}</div>`
                        : nothing}
                </div>
                ${canDownload ? html`
                    <platform-button
                        variant="ghost"
                        density="dense"
                        icon-only
                        .ariaLabel=${this.t('download_attachment')}
                        @click=${() => this._downloadAttachment(att)}
                    >
                        <platform-icon name="download" size="16"></platform-icon>
                    </platform-button>
                ` : nothing}
            </div>
        `;
    }

    _renderThreadAttachments(attachments) {
        if (!Array.isArray(attachments) || attachments.length === 0) {
            return nothing;
        }
        const fileRefs = this._attachmentFileRefs(attachments);
        const inlineRows = this._attachmentsWithoutFileId(attachments);
        return html`
            <div class="thread-attachments">
                <div class="thread-attachments-title">${this.t('attachments')}</div>
                ${fileRefs.length > 0 ? html`
                    <platform-file-attachments
                        readonly
                        layout="tiles"
                        open-source="platform.mail"
                        .files=${fileRefs}
                    ></platform-file-attachments>
                ` : nothing}
                ${inlineRows.length > 0 ? html`
                    <div class="inline-att-list">
                        ${inlineRows.map((att) => this._renderInlineAttachmentRow(att))}
                    </div>
                ` : nothing}
            </div>
        `;
    }

    _renderMessageBody(bodyText) {
        if (typeof bodyText !== 'string' || bodyText.length === 0) {
            return nothing;
        }
        const rendered = flowsChatMarkdownToHtml(bodyText, { streaming: false });
        return html`<div class="thread-body-text">${unsafeHTML(rendered)}</div>`;
    }

    _upcomingEvents() {
        const now = Date.now();
        const events = this._calendarSelect.value.events;
        return events
            .filter((ev) => {
                if (!ev || typeof ev.start_at !== 'string') return false;
                const ts = Date.parse(ev.start_at);
                return Number.isFinite(ts) && ts >= now;
            })
            .slice(0, 4);
    }

    _renderRail() {
        return html`
            <platform-mail-calendar-rail
                surface="mail"
                show-settings
                @settings-click=${() => this._openSettings()}
            ></platform-mail-calendar-rail>
        `;
    }

    _renderNav(mail, active) {
        const upcoming = this._upcomingEvents();
        const selectableFolders = mail.folders.filter((folder) => folder.selectable !== false);
        const missingRoles = mail.missingStandardRoles;
        return html`
            <nav class="mail-nav">
                <div class="nav-account">
                    <span class="nav-account-label">${this.t('account_label')}</span>
                    <span class="nav-account-email">${active ? active.email_address : this.t('empty_mailboxes')}</span>
                </div>
                <platform-button class="nav-compose" variant="primary" @click=${() => this._startCompose()}>
                    <platform-icon name="edit" size="16"></platform-icon>
                    ${this.t('compose_new')}
                </platform-button>
                <div class="nav-section-title">${this.t('folders_section')}</div>
                <div class="nav-folders">
                    ${selectableFolders.length === 0
                        ? html`<div class="empty empty-nav">${this.t('empty_folders')}</div>`
                        : selectableFolders.map((folder) => {
                            const unseen = typeof folder.unseen_count === 'number' ? folder.unseen_count : 0;
                            return html`
                            <button
                                class="folder-btn ${mail.folder === folder.name ? 'active' : ''}"
                                type="button"
                                @click=${() => this._selectFolder(folder.name)}
                            >
                                <span class="folder-icon">
                                    <platform-icon name=${this._folderIcon(folder)} size="16"></platform-icon>
                                </span>
                                <span class="folder-label">${this._folderLabel(folder)}</span>
                                ${unseen > 0
                                    ? html`<span class="folder-unseen">${unseen}</span>`
                                    : nothing}
                            </button>
                        `;
                        })}
                    ${missingRoles.length > 0 ? html`
                        <platform-button variant="ghost" @click=${() => this._ensureStandardFolders()}>
                            ${this.t('ensure_folders')}
                        </platform-button>
                    ` : nothing}
                </div>
                <div class="upcoming">
                    <div class="upcoming-title">${this.t('upcoming_meetings')}</div>
                    ${upcoming.length === 0
                        ? html`<div class="empty empty-nav">${this.t('upcoming_empty')}</div>`
                        : upcoming.map((ev) => html`
                            <button class="upcoming-item" type="button" @click=${() => this.openModal('platform.calendar', {})}>
                                <span class="upcoming-time">${formatPlatformTime(ev.start_at, this._localeTag())}</span>
                                <strong>${ev.title}</strong>
                            </button>
                        `)}
                    <platform-button variant="ghost" @click=${() => this.openModal('platform.calendar', {})}>
                        ${this.t('open_calendar')}
                    </platform-button>
                </div>
            </nav>
        `;
    }

    _renderThreadListAvatars(participants) {
        const shown = participants.slice(0, 3);
        return html`
            <span class="msg-avatars" aria-hidden="true">
                ${shown.map((address, index) => {
                    const parsed = parseMailAddress(address);
                    const hue = hueFromString(parsed.seed);
                    return html`
                        <span
                            class="msg-avatar"
                            style="background: hsl(${hue} 55% 45%); z-index: ${shown.length - index};"
                        >
                            ${initialsFromName(parsed.seed)}
                        </span>
                    `;
                })}
            </span>
        `;
    }

    _renderThreadPreview(thread, mail) {
        const items = this._previewItemsForThread(thread, mail);
        const loading = mail.selectedThreadId === thread.threadId
            && mail.messageLoading === true
            && items === thread.messages;
        return html`
            <div class="thread-preview">
                ${loading
                    ? html`
                        <div class="thread-preview-loading">
                            <platform-spinner size="sm"></platform-spinner>
                            <span>${this.t('loading')}</span>
                        </div>
                    `
                    : nothing}
                ${items.map((msg) => {
                    const parsed = parseMailAddress(msg.from_address);
                    const hue = hueFromString(parsed.seed);
                    const fromLabel = parsed.display.length > 0 ? parsed.display : this.t('empty_sender');
                    const mine = this._isMineMessage(msg, mail);
                    const snippet = typeof msg.snippet === 'string' && msg.snippet.length > 0
                        ? msg.snippet
                        : (typeof msg.body_text === 'string' && msg.body_text.length > 0
                            ? msg.body_text
                            : (typeof msg.subject === 'string' ? msg.subject : ''));
                    return html`
                        <div class="thread-preview-item ${mine ? 'mine' : 'theirs'}">
                            ${mine ? nothing : html`
                                <span class="msg-avatar" style="background: hsl(${hue} 55% 45%);">
                                    ${initialsFromName(parsed.seed)}
                                </span>
                            `}
                            <div class="thread-preview-bubble">
                                <div class="thread-preview-from">${fromLabel}</div>
                                ${snippet.length > 0
                                    ? html`<div class="thread-preview-text">${snippet}</div>`
                                    : nothing}
                            </div>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    _renderList(mail) {
        const currentFolder = mail.folders.find((folder) => folder.name === mail.folder);
        const listTitle = currentFolder
            ? this._folderLabel(currentFolder)
            : (mail.folder ? mail.folder : this.t('folder_inbox'));
        const threads = this._filteredThreads(mail);
        const unreadInList = threads.reduce((sum, thread) => sum + thread.unreadCount, 0);
        const listMeta = unreadInList > 0
            ? `${this.t(messagesCountKey(threads.length), { count: threads.length })} · ${this.t(unreadCountKey(unreadInList), { count: unreadInList })}`
            : this.t(messagesCountKey(threads.length), { count: threads.length });
        const expanded = new Set(Array.isArray(this._expandedThreadIds) ? this._expandedThreadIds : []);
        return html`
            <section class="mail-list">
                <div class="mail-list-header">
                    <div class="mail-list-header-top">
                        <div class="list-header-copy">
                            <span class="list-header-title">${listTitle}</span>
                            <span class="list-header-meta">${listMeta}</span>
                        </div>
                        <div class="header-actions">
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                .ariaLabel=${this.t('refresh')}
                                @click=${() => this._refreshMessages()}
                            >
                                <platform-icon name="refresh" size="16"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                .ariaLabel=${this.t('modal_close')}
                                @click=${() => this.close()}
                            >
                                <platform-icon name="close" size="16"></platform-icon>
                            </platform-button>
                        </div>
                    </div>
                    <input
                        class="list-search"
                        type="search"
                        data-canon="search-as-you-type"
                        .value=${this._listQuery}
                        placeholder=${this.t('search_placeholder')}
                        @input=${(e) => this._onListSearchInput(e)}
                    />
                </div>
                <div class="mail-list-body">
                    ${mail.needsSync && !mail.loading
                        ? html`<div class="empty">${this.t('needs_sync_hint')}</div>`
                        : nothing}
                    ${mail.loading
                        ? html`
                            <div class="pane-loading">
                                <platform-spinner size="md"></platform-spinner>
                                <span>${this.t('loading')}</span>
                            </div>
                        `
                        : nothing}
                    ${!mail.loading && mail.messages.length === 0
                        ? html`<div class="empty">${this.t('empty_messages')}</div>`
                        : nothing}
                    ${!mail.loading && mail.messages.length > 0 && threads.length === 0
                        ? html`<div class="empty">${this.t('search_empty')}</div>`
                        : nothing}
                    ${!mail.loading
                        ? threads.map((thread) => {
                        const latest = thread.latest;
                        const lead = parseMailAddress(
                            thread.participants[0] || latest.from_address,
                        );
                        const fromLabel = lead.display.length > 0 ? lead.display : this.t('empty_sender');
                        const subjectLabel = thread.subject.length > 0
                            ? thread.subject
                            : this.t('empty_subject');
                        const snippet = typeof latest.snippet === 'string' ? latest.snippet : '';
                        const unread = thread.unreadCount > 0;
                        const attachCount = thread.attachmentCount;
                        const dateLabel = formatMailListDate(latest.date, this._localeTag());
                        const active = mail.selectedThreadId === thread.threadId
                            || (mail.selectedUid != null
                                && thread.messages.some((msg) => msg.uid === mail.selectedUid));
                        const isExpanded = expanded.has(thread.threadId);
                        const previewItems = this._previewItemsForThread(thread, mail);
                        const count = previewItems.length;
                        return html`
                            <div class="thread-row-wrap">
                                <div
                                    class="msg-row ${active ? 'active' : ''} ${unread ? 'unread' : ''}"
                                    role="button"
                                    tabindex="0"
                                    @click=${() => this._selectThread(thread)}
                                    @keydown=${(event) => {
                                        if (event.key === 'Enter' || event.key === ' ') {
                                            event.preventDefault();
                                            this._selectThread(thread);
                                        }
                                    }}
                                >
                                    <span class="msg-unread-dot ${unread ? '' : 'is-read'}" aria-hidden="true"></span>
                                    ${this._renderThreadListAvatars(thread.participants)}
                                    <div class="msg-main">
                                        <div class="msg-top">
                                            <div class="msg-from">${fromLabel}</div>
                                            ${count > 1
                                                ? html`<span class="msg-count">(${count})</span>`
                                                : nothing}
                                            ${count > 1 ? html`
                                                <button
                                                    class="thread-expand"
                                                    type="button"
                                                    aria-expanded=${isExpanded ? 'true' : 'false'}
                                                    .ariaLabel=${isExpanded
                                                        ? this.t('hide_thread_preview')
                                                        : this.t('show_thread_preview')}
                                                    @click=${(event) => this._toggleThreadExpand(thread, event)}
                                                >
                                                    <platform-icon name="chevron-down" size="14"></platform-icon>
                                                </button>
                                            ` : nothing}
                                            ${attachCount > 0 ? html`
                                                <span
                                                    class="msg-indicators"
                                                    title=${this.t('attachment_count', { count: attachCount })}
                                                >
                                                    <platform-icon name="attach" size="14"></platform-icon>
                                                    ${attachCount > 1
                                                        ? html`<span class="msg-attach-count">${attachCount}</span>`
                                                        : nothing}
                                                </span>
                                            ` : nothing}
                                        </div>
                                        <div class="msg-subject">${subjectLabel}</div>
                                        ${snippet.length > 0
                                            ? html`<div class="msg-snippet">${snippet}</div>`
                                            : nothing}
                                    </div>
                                    ${dateLabel.length > 0
                                        ? html`<span class="msg-date">${dateLabel}</span>`
                                        : html`<span class="msg-date" aria-hidden="true"></span>`}
                                </div>
                                ${isExpanded && count > 1 ? this._renderThreadPreview(thread, mail) : nothing}
                            </div>
                        `;
                    })
                        : nothing}
                    ${!mail.loading && mail.messagesHasMore
                        ? html`
                            <div style="padding: var(--space-3); display: flex; justify-content: center;">
                                <platform-button variant="ghost" @click=${() => this._loadMoreMessages()}>
                                    ${this.t('load_more')}
                                </platform-button>
                            </div>
                        `
                        : nothing}
                </div>
            </section>
        `;
    }

    _renderChatBubble(message, mail) {
        const parsed = parseMailAddress(message.from_address);
        const fromLabel = parsed.display.length > 0 ? parsed.display : this.t('empty_sender');
        const hue = hueFromString(parsed.seed);
        const mine = this._isMineMessage(message, mail);
        const bodyText = typeof message.body_text === 'string' ? message.body_text : '';
        const timeLabel = message.date
            ? formatPlatformDateTime(message.date, this._localeTag())
            : '';
        const attachments = Array.isArray(message.attachments) ? message.attachments : [];
        const uid = typeof message.uid === 'string' ? message.uid : '';
        const messageId = typeof message.message_id === 'string' ? message.message_id : '';
        return html`
            <div
                class="chat-bubble-row ${mine ? 'mine' : 'theirs'}"
                data-uid=${uid}
                data-message-id=${messageId}
            >
                ${mine ? nothing : html`
                    <span class="msg-avatar" style="background: hsl(${hue} 55% 45%);">
                        ${initialsFromName(parsed.seed)}
                    </span>
                `}
                <div class="chat-bubble">
                    <div class="chat-bubble-meta">
                        <span class="chat-bubble-from">${fromLabel}</span>
                        ${timeLabel.length > 0
                            ? html`<span class="chat-bubble-time">${timeLabel}</span>`
                            : nothing}
                        <platform-button
                            class="chat-bubble-reply"
                            variant="ghost"
                            icon-only
                            density="compact"
                            .ariaLabel=${this.t('reply_all')}
                            @click=${(event) => {
                                event.stopPropagation();
                                this._openReplyAllForMessage(message);
                            }}
                        >
                            <platform-icon name="reply" size="14"></platform-icon>
                        </platform-button>
                    </div>
                    ${this._renderReplyQuote(message, mail)}
                    ${this._renderMessageBody(bodyText)}
                    ${this._renderThreadAttachments(attachments)}
                </div>
            </div>
        `;
    }

    _renderReplyQuote(message, mail) {
        const inReplyTo = typeof message.in_reply_to === 'string' ? message.in_reply_to.trim() : '';
        if (!inReplyTo) {
            return nothing;
        }
        const threadMessages = Array.isArray(mail.selectedThreadMessages)
            ? mail.selectedThreadMessages
            : [];
        const parent = findThreadMessageByMessageId(threadMessages, inReplyTo);
        let who = this.t('reply_quote.previous');
        let preview = '';
        let parentUid = '';
        if (parent) {
            const parsed = parseMailAddress(parent.from_address);
            who = parsed.display.length > 0 ? parsed.display : this.t('empty_sender');
            preview = mailReplyPreviewText(parent);
            parentUid = typeof parent.uid === 'string' ? parent.uid : '';
        }
        return html`
            <button
                type="button"
                class="mail-reply-quote"
                data-parent-uid=${parentUid}
                @click=${(event) => {
                    event.stopPropagation();
                    this._scrollToThreadMessage(parentUid);
                }}
            >
                <span class="who">${who}</span>
                ${preview.length > 0
                    ? html`<span class="preview">${preview}</span>`
                    : nothing}
            </button>
        `;
    }

    _scrollToThreadMessage(uid) {
        if (typeof uid !== 'string' || !uid) {
            return;
        }
        const root = this.renderRoot;
        if (!root) {
            return;
        }
        const target = root.querySelector(`.chat-bubble-row[data-uid="${CSS.escape(uid)}"]`);
        if (!(target instanceof HTMLElement)) {
            return;
        }
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.classList.add('reply-target-flash');
        window.setTimeout(() => {
            target.classList.remove('reply-target-flash');
        }, 900);
    }

    _clearComposeReplyMode() {
        this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, {
            in_reply_to: null,
            references: null,
        });
    }

    _composeReplyModeLabel(mail) {
        const inReplyTo = typeof mail.compose.in_reply_to === 'string'
            ? mail.compose.in_reply_to.trim()
            : '';
        if (!inReplyTo) {
            return '';
        }
        const threadMessages = Array.isArray(mail.selectedThreadMessages)
            ? mail.selectedThreadMessages
            : [];
        const parent = findThreadMessageByMessageId(threadMessages, inReplyTo);
        if (!parent) {
            return this.t('compose.reply_to', { author: this.t('reply_quote.previous') });
        }
        const parsed = parseMailAddress(parent.from_address);
        const author = parsed.display.length > 0 ? parsed.display : this.t('empty_sender');
        return this.t('compose.reply_to', { author });
    }

    _renderThread(mail) {
        const threadMessages = Array.isArray(mail.selectedThreadMessages)
            ? mail.selectedThreadMessages
            : [];
        const message = this._replyTargetMessage(mail);
        const rawSubject = message && typeof message.subject === 'string' ? message.subject : '';
        const subjectLabel = rawSubject.length > 0
            ? (normalizeMailSubject(rawSubject)
                ? rawSubject.replace(/^\s*((re|fw|fwd|sv|aw|antw|ответ|пересл)\s*:\s*)+/i, '').trim() || rawSubject
                : rawSubject)
            : this.t('empty_thread');
        const hasThread = threadMessages.length > 0 || Boolean(message);
        const unreadInThread = threadMessages.some((item) => item.unread === true)
            || (message && message.unread === true);
        const composeTitle = mail.compose.in_reply_to
            ? this.t('compose_reply_title')
            : (mail.compose.subject.startsWith('Fwd:')
                ? this.t('compose_forward_title')
                : this.t('compose_new_title'));
        const composeReplyModeLabel = this._composeReplyModeLabel(mail);
        return html`
            <section class="mail-thread">
                <div class="mail-thread-header">
                    <div class="thread-actions">
                        <platform-button
                            class="thread-back"
                            variant="ghost"
                            icon-only
                            density="compact"
                            .ariaLabel=${this.t('back_to_list')}
                            @click=${() => { this._mobilePane = 'list'; }}
                        >
                            <platform-icon name="arrow-left" size="16"></platform-icon>
                        </platform-button>
                        ${hasThread && !unreadInThread ? html`
                            <platform-button
                                variant="ghost"
                                density="compact"
                                @click=${() => this._markSelectedUnseen()}
                            >
                                ${this.t('mark_unread')}
                            </platform-button>
                        ` : nothing}
                        ${hasThread ? html`
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                .ariaLabel=${this.t('action_star')}
                                @click=${() => this._toggleStarSelected()}
                            >
                                <platform-icon name="star" size="16"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                .ariaLabel=${this.t('action_archive')}
                                @click=${() => this._archiveSelected()}
                            >
                                <platform-icon name="folder" size="16"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                .ariaLabel=${this.t('action_trash')}
                                @click=${() => this._trashSelected()}
                            >
                                <platform-icon name="trash" size="16"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                density="compact"
                                @click=${() => this._deleteSelectedForever()}
                            >
                                ${this.t('action_delete_forever')}
                            </platform-button>
                        ` : nothing}
                    </div>
                    <div class="header-actions">
                        <span class="shortcuts-hint">${this.t('shortcuts_hint')}</span>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="compact"
                            .ariaLabel=${this.t('modal_close')}
                            @click=${() => this.close()}
                        >
                            <platform-icon name="close" size="16"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <div class="mail-thread-scroll">
                    ${mail.messageLoading
                        ? html`
                            <div class="pane-loading">
                                <platform-spinner size="md"></platform-spinner>
                                <span>${this.t('loading')}</span>
                            </div>
                        `
                        : !hasThread
                        ? html`
                            <div class="empty-thread">
                                <div class="empty-thread-title">${this.t('empty_thread')}</div>
                                <div>${this.t('empty_thread_hint')}</div>
                                <platform-button variant="primary" @click=${() => this._startCompose()}>
                                    <platform-icon name="edit" size="16"></platform-icon>
                                    ${this.t('compose_new')}
                                </platform-button>
                            </div>
                        `
                        : html`
                            <div class="thread-meta">
                                <div class="thread-subject">${subjectLabel}</div>
                                <div class="thread-subject-meta">
                                    ${this.t('thread_messages_count', {
                                        count: Math.max(threadMessages.length, 1),
                                    })}
                                </div>
                            </div>
                            <div class="chat-stream">
                                ${(threadMessages.length > 0 ? threadMessages : [message]).map(
                                    (item) => this._renderChatBubble(item, mail),
                                )}
                            </div>
                        `}
                </div>
                ${hasThread && !this._composeOpen ? html`
                    <div class="reply-bar">
                        <input
                            class="reply-bar-input"
                            type="text"
                            data-canon="composer"
                            .value=${this._quickReplyText}
                            .placeholder=${this.t('reply_bar_hint')}
                            @input=${(e) => this._onQuickReplyInput(e)}
                            @keydown=${(e) => this._onQuickReplyKeydown(e)}
                        />
                        <div class="thread-actions">
                            <platform-button variant="primary" @click=${() => this._submitQuickReply()}>
                                <platform-icon name="reply" size="16"></platform-icon>
                                ${this.t('reply')}
                            </platform-button>
                            <platform-button variant="secondary" @click=${() => this._openReplyAll()}>
                                ${this.t('reply_all')}
                            </platform-button>
                            <platform-button variant="ghost" @click=${() => this._openForward()}>
                                ${this.t('forward')}
                            </platform-button>
                        </div>
                    </div>
                ` : nothing}
                ${this._composeOpen ? html`
                    <div
                        class="compose"
                        style=${this._composePanelStyle()}
                        data-expanded=${this._composeExpanded ? 'true' : 'false'}
                        data-dragging=${this._composeDragging ? 'true' : 'false'}
                        data-resizing=${this._composeResizing ? 'true' : 'false'}
                    >
                        <div
                            class="compose-header"
                            @pointerdown=${(e) => this._onComposeHeaderPointerDown(e)}
                        >
                            <span class="compose-title">${composeTitle}</span>
                            <div class="compose-header-actions">
                                <platform-button
                                    variant="ghost"
                                    icon-only
                                    density="dense"
                                    .ariaLabel=${this._composeExpanded
                                        ? this.t('compose_restore')
                                        : this.t('compose_expand')}
                                    @click=${() => this._toggleComposeExpanded()}
                                >
                                    <platform-icon
                                        name=${this._composeExpanded ? 'collapse' : 'expand'}
                                        size="14"
                                    ></platform-icon>
                                </platform-button>
                                <platform-button
                                    variant="ghost"
                                    icon-only
                                    density="dense"
                                    .ariaLabel=${this.t('compose_discard')}
                                    @click=${() => this._closeCompose()}
                                >
                                    <platform-icon name="close" size="14"></platform-icon>
                                </platform-button>
                            </div>
                        </div>
                        ${composeReplyModeLabel
                            ? html`
                                <div class="compose-reply-mode">
                                    <span class="compose-reply-mode-label">${composeReplyModeLabel}</span>
                                    <platform-button
                                        variant="ghost"
                                        icon-only
                                        density="dense"
                                        .ariaLabel=${this.t('compose_discard')}
                                        @click=${() => this._clearComposeReplyMode()}
                                    >
                                        <platform-icon name="close" size="14"></platform-icon>
                                    </platform-button>
                                </div>
                            `
                            : nothing}
                        <div class="compose-meta">
                            <label class="compose-row">
                                <span class="compose-row-label">${this.t('to_label')}</span>
                                <input
                                    class="compose-input"
                                    type="email"
                                    data-canon="composer"
                                    .value=${mail.compose.to}
                                    @input=${(e) => this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, { to: e.target.value })}
                                />
                            </label>
                            <label class="compose-row">
                                <span class="compose-row-label">${this.t('subject_label')}</span>
                                <input
                                    class="compose-input"
                                    type="text"
                                    data-canon="composer"
                                    .value=${mail.compose.subject}
                                    @input=${(e) => this.dispatch(MAIL_EVENTS.COMPOSE_DRAFT_SET, { subject: e.target.value })}
                                />
                            </label>
                        </div>
                        <platform-markdown-editor
                            variant="compose"
                            view-mode="wysiwyg"
                            .htmlValue=${typeof mail.compose.body_html === 'string' && mail.compose.body_html.length > 0
                                ? mail.compose.body_html
                                : (mail.compose.body || '')}
                            .attachments=${Array.isArray(mail.compose.attachments) ? mail.compose.attachments : []}
                            .placeholder=${this.t('compose_placeholder')}
                            .primaryLabel=${this.t('send')}
                            ?show-primary=${true}
                            ?show-attach=${true}
                            ?show-discard=${true}
                            ?show-format-toggle=${true}
                            ?primary-disabled=${mail.sending}
                            @change=${(e) => this._onEditorChange(e)}
                            @attachments-change=${(e) => this._onEditorAttachmentsChange(e)}
                            @primary=${() => this._sendReply()}
                            @discard=${() => this._closeCompose()}
                        ></platform-markdown-editor>
                        ${this._composeExpanded ? nothing : html`
                            <div
                                class="compose-resize-handle"
                                role="separator"
                                aria-orientation="both"
                                aria-label=${this.t('compose_resize')}
                                @pointerdown=${(e) => this._onComposeResizePointerDown(e)}
                            ></div>
                        `}
                    </div>
                ` : nothing}
            </section>
        `;
    }

    _renderMyBindingRow(binding) {
        const isRole = binding.kind === 'role';
        return html`
            <div class="settings-row">
                <div class="settings-row-main">
                    <div class="settings-row-meta">
                        <div class="binding-email">${binding.email_address}</div>
                        ${isRole
                            ? html`<span class="att-badge">${this.t('binding_kind_role')}</span>`
                            : nothing}
                        ${binding.is_default
                            ? html`<span class="att-badge">${this.t('default_badge')}</span>`
                            : nothing}
                    </div>
                    <div class="binding-color">
                        <platform-palette-color-picker
                            .value=${binding.calendar_color || 'default'}
                            @change=${(e) => this._patchBindingColor(binding.mailbox_binding_id, e.detail.value)}
                        ></platform-palette-color-picker>
                    </div>
                    ${!isRole && !binding.is_default ? html`
                        <div class="binding-actions">
                            <platform-button
                                variant="ghost"
                                @click=${() => this.dispatch(MAIL_EVENTS.DEFAULT_SET_REQUESTED, {
                                    mailbox_binding_id: binding.mailbox_binding_id,
                                })}
                            >${this.t('set_default')}</platform-button>
                        </div>
                    ` : nothing}
                </div>
            </div>
        `;
    }

    _ensureRoleMembersLoaded(mailboxBindingId) {
        const mail = this._mailSelect.value;
        if (mail.bindingMembers && Array.isArray(mail.bindingMembers[mailboxBindingId])) {
            return;
        }
        this.dispatch(MAIL_EVENTS.BINDING_MEMBERS_LOAD_REQUESTED, {
            mailbox_binding_id: mailboxBindingId,
        });
    }

    _renderRoleMembers(binding, memberOptions) {
        const mail = this._mailSelect.value;
        const members = (
            mail.bindingMembers && Array.isArray(mail.bindingMembers[binding.mailbox_binding_id])
        )
            ? mail.bindingMembers[binding.mailbox_binding_id]
            : [];
        return html`
            <div class="settings-members">
                <div class="settings-hint">${this.t('role_members_hint')}</div>
                ${members.map((member) => html`
                    <div class="settings-member-row">
                        <platform-user-chip user-id=${member.user_id} size="sm"></platform-user-chip>
                        <platform-button
                            variant="ghost"
                            @click=${() => this.dispatch(MAIL_EVENTS.BINDING_MEMBER_REMOVE_REQUESTED, {
                                mailbox_binding_id: binding.mailbox_binding_id,
                                user_id: member.user_id,
                            })}
                        >${this.t('role_member_remove')}</platform-button>
                    </div>
                `)}
                <div class="settings-row-form">
                    <platform-field
                        type="enum"
                        .label=${this.t('role_member_add')}
                        .value=${this._memberDraftUserId}
                        .config=${{ values: memberOptions }}
                        mode="edit"
                        @change=${(e) => { this._memberDraftUserId = e.detail.value; }}
                    ></platform-field>
                    <platform-button
                        variant="secondary"
                        @click=${() => {
                            const userId = this._memberDraftUserId.trim();
                            if (!userId) {
                                this.toast('assign_user_required', { type: 'warning' });
                                return;
                            }
                            this.dispatch(MAIL_EVENTS.BINDING_MEMBER_ADD_REQUESTED, {
                                mailbox_binding_id: binding.mailbox_binding_id,
                                user_id: userId,
                                role: 'member',
                            });
                            this._memberDraftUserId = '';
                        }}
                    >${this.t('role_member_add')}</platform-button>
                </div>
            </div>
        `;
    }

    _renderCompanyBindingRow(binding, memberOptions) {
        const isRole = binding.kind === 'role';
        const assigned = typeof binding.user_id === 'string' && binding.user_id.length > 0;
        const assignLabel = assigned ? this.t('reassign_binding') : this.t('assign_binding');
        return html`
            <div class="settings-row">
                <div class="settings-row-main">
                    <div class="settings-row-meta">
                        <div class="binding-email">${binding.email_address}</div>
                        ${isRole
                            ? html`<span class="att-badge">${this.t('binding_kind_role')}</span>`
                            : nothing}
                        ${!isRole && assigned
                            ? html`<platform-user-chip user-id=${binding.user_id} size="sm"></platform-user-chip>`
                            : (!isRole
                                ? html`<span class="binding-unassigned">${this.t('binding_unassigned')}</span>`
                                : nothing)}
                        ${binding.is_default && assigned
                            ? html`<span class="att-badge">${this.t('default_badge')}</span>`
                            : nothing}
                    </div>
                    <div class="binding-color">
                        <platform-palette-color-picker
                            .value=${binding.calendar_color || 'default'}
                            @change=${(e) => this._patchBindingColor(binding.mailbox_binding_id, e.detail.value)}
                        ></platform-palette-color-picker>
                    </div>
                    <div class="binding-actions">
                        ${assigned && !binding.is_default && !isRole ? html`
                            <platform-button
                                variant="ghost"
                                @click=${() => this.dispatch(MAIL_EVENTS.DEFAULT_SET_REQUESTED, {
                                    mailbox_binding_id: binding.mailbox_binding_id,
                                })}
                            >${this.t('set_default_for_user')}</platform-button>
                        ` : nothing}
                        <platform-button
                            variant="danger"
                            @click=${() => { void this._confirmUnbind(binding); }}
                        >${this.t('unbind')}</platform-button>
                    </div>
                </div>
                ${isRole
                    ? this._renderRoleMembers(binding, memberOptions)
                    : html`
                        <div class="settings-row-form">
                            <platform-field
                                type="enum"
                                .label=${this.t('assign_user')}
                                .value=${this._assignDraftFor(binding)}
                                .config=${{ values: memberOptions }}
                                mode="edit"
                                @change=${(e) => this._setAssignDraft(binding.mailbox_binding_id, e.detail.value)}
                            ></platform-field>
                            <platform-button
                                variant="secondary"
                                @click=${() => this._assignCompanyBinding(binding)}
                            >${assignLabel}</platform-button>
                        </div>
                    `}
            </div>
        `;
    }

    _renderSettings(mail) {
        if (!mail.adminMode || !this._adminDraft) return nothing;
        const isAdmin = this._isCompanyAdmin();
        const memberOptions = this._memberOptions();
        return html`
            <div class="settings-overlay">
                <div class="settings-panel">
                    <div class="settings-header">
                        <div class="settings-header-title">${this.t('settings_title')}</div>
                        <button
                            type="button"
                            class="btn-icon"
                            @click=${() => this._closeSettings()}
                            title=${this.t('settings_close')}
                            aria-label=${this.t('settings_close')}
                        >
                            <platform-icon name="close" size="16"></platform-icon>
                        </button>
                    </div>
                    <div class="settings-body">
                        <div class="settings-hint">${this.t('settings_reading_hint')}</div>
                        <section class="settings-section">
                            <div class="settings-section-title">${this.t('my_bindings_title')}</div>
                            <div class="settings-hint">${this.t('my_bindings_hint')}</div>
                            ${mail.bindings.length === 0
                                ? html`<div class="empty">${this.t('my_bindings_empty')}</div>`
                                : mail.bindings.map((binding) => this._renderMyBindingRow(binding))}
                        </section>
                        ${isAdmin ? html`
                            <section class="settings-section">
                                <div class="settings-section-title">${this.t('company_bindings_title')}</div>
                                <div class="settings-hint">${this.t('company_bindings_hint')}</div>
                                ${mail.companyBindings.length === 0
                                    ? html`<div class="empty">${this.t('bindings_empty')}</div>`
                                    : mail.companyBindings.map((binding) => this._renderCompanyBindingRow(binding, memberOptions))}
                                <div class="settings-create-card">
                                    <div class="settings-section-title">${this.t('create_binding_title')}</div>
                                    <platform-field
                                        type="enum"
                                        .label=${this.t('binding_kind_label')}
                                        .value=${this._createKind}
                                        .config=${{ values: [
                                            { value: 'user', label: this.t('binding_kind_user') },
                                            { value: 'role', label: this.t('binding_kind_role') },
                                        ] }}
                                        mode="edit"
                                        @change=${(e) => { this._createKind = e.detail.value; }}
                                    ></platform-field>
                                    <platform-field
                                        type="string"
                                        .label=${this.t('local_part')}
                                        .value=${this._createLocalPart}
                                        mode="edit"
                                        @change=${(e) => { this._createLocalPart = e.detail.value; }}
                                    ></platform-field>
                                    ${this._createKind === 'role' ? nothing : html`
                                        <platform-field
                                            type="enum"
                                            .label=${this.t('assign_user')}
                                            .value=${this._createUserId}
                                            .config=${{ values: memberOptions }}
                                            mode="edit"
                                            @change=${(e) => { this._createUserId = e.detail.value; }}
                                        ></platform-field>
                                    `}
                                    <platform-button variant="accent" @click=${() => this._createBinding()}>
                                        ${this.t('create_binding')}
                                    </platform-button>
                                </div>
                            </section>
                            <section class="settings-section">
                                <div class="settings-section-title">${this.t('connection_title')}</div>
                                ${mail.connection === null && !this._adminDraft.mail_domain
                                    ? html`<div class="empty">${this.t('connection_missing')}</div>`
                                    : nothing}
                                <platform-field type="string" .label=${this.t('connection_domain')} .value=${this._adminDraft.mail_domain}
                                    mode="edit" @change=${(e) => { this._adminDraft = { ...this._adminDraft, mail_domain: e.detail.value }; }}></platform-field>
                                <platform-field type="enum" .label=${this.t('connection_provider')} .value=${this._adminDraft.provider}
                                    .config=${{ values: [
                                        { value: 'ispmanager', label: this.t('provider_ispmanager') },
                                        { value: 'generic_imap_smtp', label: this.t('provider_generic') },
                                    ] }}
                                    mode="edit" @change=${(e) => { this._adminDraft = { ...this._adminDraft, provider: e.detail.value }; }}></platform-field>
                                <platform-field type="string" .label=${this.t('connection_imap')} .value=${this._adminDraft.imap_host}
                                    mode="edit" @change=${(e) => { this._adminDraft = { ...this._adminDraft, imap_host: e.detail.value }; }}></platform-field>
                                <platform-field type="integer" .label=${this.t('connection_imap_port')} .value=${this._adminDraft.imap_port}
                                    mode="edit" @change=${(e) => { this._adminDraft = { ...this._adminDraft, imap_port: e.detail.value }; }}></platform-field>
                                <platform-field type="string" .label=${this.t('connection_smtp')} .value=${this._adminDraft.smtp_host}
                                    mode="edit" @change=${(e) => { this._adminDraft = { ...this._adminDraft, smtp_host: e.detail.value }; }}></platform-field>
                                <platform-field type="integer" .label=${this.t('connection_smtp_port')} .value=${this._adminDraft.smtp_port}
                                    mode="edit" @change=${(e) => { this._adminDraft = { ...this._adminDraft, smtp_port: e.detail.value }; }}></platform-field>
                                <div class="header-actions">
                                    <platform-button variant="primary" @click=${() => this._saveConnection()}>${this.t('connection_save')}</platform-button>
                                    <platform-button variant="secondary" @click=${() => this.dispatch(MAIL_EVENTS.HEALTHCHECK_REQUESTED, null)}>${this.t('healthcheck')}</platform-button>
                                </div>
                            </section>
                        ` : nothing}
                    </div>
                </div>
            </div>
        `;
    }

    renderBody() {
        const mail = this._mailSelect.value;
        const active = this._activeBinding();
        return html`
            <div class="mail-shell-wrap">
                <div class="mail-shell" data-pane=${this._mobilePane}>
                    ${this._renderRail()}
                    ${this._renderNav(mail, active)}
                    ${this._renderList(mail)}
                    ${this._renderThread(mail)}
                </div>
                ${this._renderSettings(mail)}
            </div>
        `;
    }
}

customElements.define('platform-mail-modal', PlatformMailModal);
registerModalKind(PlatformMailModal.modalKind, 'platform-mail-modal');
