/**
 * Session files tray for Flow UI chrome (top-actions).
 * Lists FileRefs from the active context; click opens platform.file_viewer.
 * Thumbnails use core file-type icons — never authenticated download URLs as <img>.
 */

import { LitElement, css, html, nothing } from '../../lit-shim.js';
import type { FlowUiRecord } from '../runtime/flow-ui-store.js';
import { formatFileSize } from '../../utils/format-file-size.js';
import { resolveFileIconKey } from '../../utils/file-icons.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';
import { openFlowUISessionFile } from '../utils/open-session-file.js';
import '../../components/platform-icon.js';

function asFileList(value: unknown): FlowUiRecord[] {
    return Array.isArray(value) ? value : [];
}

function fileLabel(file: FlowUiRecord): string {
    if (!file || typeof file !== 'object') {
        throw new Error('flow-ui-files-panel: file object required');
    }
    if (typeof file.original_name === 'string' && file.original_name.trim() !== '') {
        return file.original_name.trim();
    }
    if (typeof file.filename === 'string' && file.filename.trim() !== '') {
        return file.filename.trim();
    }
    if (typeof file.file_id === 'string' && file.file_id.trim() !== '') {
        return file.file_id.trim();
    }
    throw new Error('flow-ui-files-panel: FileRef missing original_name/filename/file_id');
}

function fileContentType(file: FlowUiRecord): string {
    return typeof file.content_type === 'string' ? file.content_type : '';
}

export class FlowUIFilesPanel extends LitElement {
    declare files: FlowUiRecord[];
    declare locale: string;
    declare _expanded: boolean;

    static override properties = {
        files: { attribute: false },
        locale: { type: String },
        _expanded: { state: true },
    };

    static override styles = css`
        :host {
            display: block;
            position: relative;
            z-index: 1;
            pointer-events: auto;
        }
        .widget {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }
        .trigger {
            height: 36px;
            min-height: 36px;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 0 12px;
            border: 1px solid var(--flow-ui-border, var(--glass-border-subtle));
            border-radius: 999px;
            background: color-mix(in srgb, var(--flow-ui-panel-strong, var(--bg-primary, #fff)) 92%, transparent);
            color: var(--flow-ui-text, var(--text-primary));
            box-shadow: var(--flow-ui-panel-shadow, 0 14px 34px rgba(15, 23, 42, 0.12));
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            cursor: pointer;
            font: inherit;
            font-size: 13px;
            font-weight: 650;
            transform: none;
            filter: none;
        }
        .trigger:hover {
            border-color: color-mix(in srgb, var(--flow-ui-accent) 40%, var(--flow-ui-border));
            transform: none;
            filter: none;
        }
        .count {
            color: var(--flow-ui-muted, var(--text-tertiary));
            font-weight: 500;
        }
        .tray {
            position: absolute;
            top: calc(100% + 8px);
            right: 0;
            z-index: 10;
            width: min(320px, calc(100vw - 28px));
            max-height: min(360px, 50vh);
            overflow: auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 8px;
            border: 1px solid var(--flow-ui-border-strong, var(--glass-border-medium));
            border-radius: var(--radius-xl, 18px);
            background: var(--flow-ui-panel-strong, var(--glass-solid-strong, var(--bg-primary)));
            box-shadow: var(--flow-ui-panel-shadow, var(--glass-shadow-strong));
        }
        .file-row {
            min-height: 44px;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 8px 10px;
            border: 1px solid var(--flow-ui-border, var(--glass-border-subtle));
            border-radius: 14px;
            background: color-mix(in srgb, var(--flow-ui-surface, transparent) 80%, transparent);
            color: inherit;
            cursor: pointer;
            text-align: left;
            font: inherit;
            font-weight: 500;
            transform: none;
            filter: none;
        }
        .file-row:hover {
            border-color: color-mix(in srgb, var(--flow-ui-accent) 45%, var(--flow-ui-border));
            background: var(--flow-ui-surface-hover, var(--glass-tint-subtle));
            transform: none;
            filter: none;
        }
        .file-meta {
            min-width: 0;
            display: grid;
            gap: 2px;
        }
        .file-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 13px;
            color: var(--flow-ui-heading, var(--text-primary));
        }
        .file-size {
            font-size: 11px;
            color: var(--flow-ui-muted, var(--text-tertiary));
        }
        .thumb {
            width: 34px;
            height: 34px;
            flex-shrink: 0;
            border-radius: 10px;
            overflow: hidden;
            display: grid;
            place-items: center;
            background: color-mix(in srgb, var(--flow-ui-surface, #fff) 70%, transparent);
            color: var(--flow-ui-muted);
        }
    `;

    constructor() {
        super();
        this.files = [];
        this.locale = 'ru';
        this._expanded = false;
    }

    _locale() {
        return resolveFlowUILocale(this.locale);
    }

    private _toggle(event?: Event) {
        event?.stopPropagation?.();
        this._expanded = !this._expanded;
    }

    private _open(file: FlowUiRecord, event?: Event) {
        event?.stopPropagation?.();
        openFlowUISessionFile(file, 'flow_ui_files_panel');
        this._expanded = false;
    }

    private _renderFile(file: FlowUiRecord) {
        const name = fileLabel(file);
        const size = typeof file.file_size === 'number' ? file.file_size : NaN;
        const iconKey = resolveFileIconKey(name, fileContentType(file));
        return html`
            <button
                type="button"
                class="file-row"
                title=${name}
                @click=${(event: Event) => this._open(file, event)}
            >
                <span class="file-meta">
                    <span class="file-name">${name}</span>
                    ${Number.isFinite(size) && size > 0
                        ? html`<span class="file-size">${formatFileSize(size)}</span>`
                        : nothing}
                </span>
                <span class="thumb">
                    <platform-icon file-icon name=${iconKey} size="20"></platform-icon>
                </span>
            </button>
        `;
    }

    override render() {
        const files = asFileList(this.files);
        if (files.length === 0) return nothing;
        const locale = this._locale();
        return html`
            <div class="widget" @click=${(event: Event) => event.stopPropagation()}>
                <button
                    type="button"
                    class="trigger"
                    aria-expanded=${this._expanded ? 'true' : 'false'}
                    aria-label=${flowUIText(locale, 'session_files_panel', { count: String(files.length) })}
                    @click=${(event: Event) => this._toggle(event)}
                >
                    <platform-icon name="paperclip" size="16"></platform-icon>
                    <span>${flowUIText(locale, 'session_files')}
                        <span class="count">${files.length}</span>
                    </span>
                    <platform-icon name=${this._expanded ? 'chevron-up' : 'chevron-down'} size="14"></platform-icon>
                </button>
                ${this._expanded
                    ? html`<div class="tray" role="list">${files.map((file) => this._renderFile(file))}</div>`
                    : nothing}
            </div>
        `;
    }
}

if (!customElements.get('flow-ui-files-panel')) {
    customElements.define('flow-ui-files-panel', FlowUIFilesPanel);
}
