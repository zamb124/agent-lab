/**
 * MessageBubble — отображение одного сообщения со всеми типами контента
 * Полный паритет с sync1 MessageBubble + MessageContentView
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { copyTextToClipboard } from '@platform/lib/utils/clipboard.js';
import { createAvatarRetry } from '@platform/lib/utils/avatar-retry.js';
import { SyncStore } from '../store/sync.store.js';
import { senderUserId } from '../utils/sender.js';
import {
    SYNC_MENTION_IN_TEXT_RE,
    mentionDisplayLabel,
    plainTextSnippetWithMentionLabels,
} from '../utils/sync-mention-text.js';
import '../modals/user-info-modal.js';
import './message-context-menu.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-audio-message-player.js';

function formatMessageTime(iso, locale) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const loc = locale === 'ru' ? 'ru-RU' : 'en-US';
    return d.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' });
}

function toShortUsername(displayName, defaultLabel) {
    const raw = (displayName || '').trim();
    if (raw === '') return defaultLabel;
    const parts = raw.split(/\s+/).filter(p => p.trim() !== '');
    const nonEmail = parts.filter(p => !p.includes('@'));
    if (nonEmail.length > 0) return nonEmail.join(' ');
    const first = parts[0] ?? raw;
    if (first.includes('@')) return first.split('@')[0] || first;
    return raw;
}

function initialsForAvatar(displayName, defaultLabel) {
    const label = toShortUsername(displayName, defaultLabel);
    if (label === defaultLabel) return '?';
    const parts = label.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
        const a = parts[0][0] ?? '';
        const b = parts[1][0] ?? '';
        return (a + b).toUpperCase();
    }
    const w = parts[0] ?? label;
    return w.slice(0, 2).toUpperCase();
}

const LONG_PRESS_MS = 450;
const LONG_PRESS_MOVE_CANCEL_PX = 12;

function hueFromUserId(userId) {
    let h = 0;
    for (let i = 0; i < userId.length; i++) {
        h = (h * 31 + userId.charCodeAt(i)) >>> 0;
    }
    return h % 360;
}

function extractPlainText(msg) {
    const contents = msg?.contents ?? [];
    const parts = [];
    for (const c of contents) {
        if (c.type === 'text/plain' && typeof c.data?.body === 'string') {
            parts.push(c.data.body);
        }
    }
    return parts.join('\n').trim();
}

/**
 * @param {string} body
 * @param {{ _openMentionProfile: (id: string) => void }} host
 * @param {(key: string, params?: Record<string, unknown>) => string} tp
 */
function renderPlainTextMessage(body, host, tp) {
    if (typeof body !== 'string') throw new Error(tp('bubble.err_plain'));
    const re = new RegExp(SYNC_MENTION_IN_TEXT_RE.source, SYNC_MENTION_IN_TEXT_RE.flags);
    const membersList = SyncStore.state.companyMembers?.list;
    const chunks = [];
    let last = 0;
    let m;
    while ((m = re.exec(body)) !== null) {
        if (m.index > last) {
            chunks.push({ kind: 'text', value: body.slice(last, m.index) });
        }
        chunks.push({ kind: 'mention', userId: m[1] });
        last = m.index + m[0].length;
    }
    if (last < body.length) {
        chunks.push({ kind: 'text', value: body.slice(last) });
    }
    if (chunks.length === 0) {
        return html`<div class="msg-text">${body}</div>`;
    }
    return html`
        <div class="msg-text">
            ${chunks.map(ch =>
                ch.kind === 'text'
                    ? ch.value
                    : html`<span
                          class="msg-mention msg-mention--interactive"
                          role="button"
                          tabindex="0"
                          title=${tp('bubble.profile_title')}
                          @pointerdown=${(e) => e.stopPropagation()}
                          @click=${(e) => {
                              e.stopPropagation();
                              host._openMentionProfile(ch.userId);
                          }}
                          @keydown=${(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  host._openMentionProfile(ch.userId);
                              }
                          }}
                      >@${mentionDisplayLabel(ch.userId, membersList)}</span>`
            )}
        </div>
    `;
}

function _formatFileSize(bytes, tp) {
    if (bytes < 1024) return tp('bubble.file_size_b', { n: bytes });
    if (bytes < 1024 * 1024) return tp('bubble.file_size_kb', { n: (bytes / 1024).toFixed(1) });
    if (bytes < 1024 * 1024 * 1024) return tp('bubble.file_size_mb', { n: (bytes / (1024 * 1024)).toFixed(1) });
    return tp('bubble.file_size_gb', { n: (bytes / (1024 * 1024 * 1024)).toFixed(1) });
}

const _svgImageDownload = html`
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 3v13M5 15l7 7 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M3 21h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`;

const _svgCallBoundaryJoin = html`
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polygon points="23 7 16 12 23 17 23 7"/>
        <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
    </svg>`;

/** file_id, которые уже вернули 404/ошибку загрузки, чтобы не дергать download повторно на каждом ререндере. */
const _unavailableFileIds = new Set();

function markFileUnavailable(fileId, tp) {
    if (typeof fileId !== 'string' || fileId === '') {
        throw new Error(tp('bubble.err_mark_file_id'));
    }
    _unavailableFileIds.add(fileId);
}

function isFileUnavailable(fileId, tp) {
    if (typeof fileId !== 'string' || fileId === '') {
        throw new Error(tp('bubble.err_check_file_id'));
    }
    return _unavailableFileIds.has(fileId);
}

/**
 * @param {object} content
 * @param {{
 *   _openMentionProfile: (id: string) => void,
 *   requestUpdate: () => void,
 *   activeCallOverlay: { call_id?: string, minimized?: boolean } | null | undefined,
 *   _joinCallFromBoundary: (callId: string) => void,
 * }} host
 * @param {(key: string, params?: Record<string, unknown>) => string} tp
 */
function _callBoundaryShowJoinButton(host, boundaryCallId) {
    const o = host.activeCallOverlay;
    if (o == null || typeof o !== 'object') return true;
    const activeId = o.call_id;
    if (typeof activeId !== 'string' || activeId === '') return true;
    if (activeId !== boundaryCallId) return true;
    return o.minimized === true;
}

function renderContent(content, host, tp) {
    if (content.type === 'text/plain') {
        const body = content.data?.body;
        if (typeof body !== 'string') throw new Error(tp('bubble.err_plain'));
        return renderPlainTextMessage(body, host, tp);
    }
    if (content.type === 'code/block') {
        const { language, source } = content.data ?? {};
        if (typeof language !== 'string' || typeof source !== 'string') {
            throw new Error(tp('bubble.err_code_block'));
        }
        return html`
            <div class="code-block">
                <div class="code-lang">${language}</div>
                <pre class="code-source"><code>${source}</code></pre>
            </div>
        `;
    }
    if (content.type === 'mock/image') {
        const fileId = content.data?.file_id;
        if (typeof fileId !== 'string') throw new Error(tp('bubble.err_mock_image'));
        if (isFileUnavailable(fileId, tp)) {
            return html`<div class="file-missing">${tp('bubble.file_missing', { id: fileId })}</div>`;
        }
        const src = `/sync/api/v1/files/download/${fileId}`;
        const alt = typeof content.data?.alt_text === 'string' ? content.data.alt_text : '';
        const dlName = alt.trim() !== '' ? alt.trim() : `image-${fileId.slice(0, 12)}`;
        return html`
            <div class="file-image-wrap">
                <div class="file-image-frame">
                    <img
                        class="file-image"
                        src=${src}
                        alt=${alt}
                        loading="lazy"
                        @error=${() => {
                            markFileUnavailable(fileId, tp);
                            host.requestUpdate();
                        }}
                    >
                    <a
                        class="file-image-dl"
                        href=${src}
                        download=${dlName}
                        target="_blank"
                        title=${tp('bubble.download_title')}
                        @click=${(e) => e.stopPropagation()}
                    >${_svgImageDownload}</a>
                </div>
            </div>
        `;
    }
    if (content.type === 'file/image') {
        const { file_id: fileId, filename } = content.data ?? {};
        if (typeof fileId !== 'string') throw new Error(tp('bubble.err_file_image'));
        if (isFileUnavailable(fileId, tp)) {
            return html`<div class="file-missing">${tp('bubble.file_missing', { id: fileId })}</div>`;
        }
        const src = `/sync/api/v1/files/download/${fileId}`;
        const label = typeof filename === 'string' && filename.trim() !== '' ? filename.trim() : `file-${fileId.slice(0, 12)}`;
        return html`
            <div class="file-image-wrap">
                <div class="file-image-frame">
                    <img
                        class="file-image"
                        src=${src}
                        alt=${label}
                        loading="lazy"
                        @error=${() => {
                            markFileUnavailable(fileId, tp);
                            host.requestUpdate();
                        }}
                    >
                    <a
                        class="file-image-dl"
                        href=${src}
                        download=${label}
                        target="_blank"
                        title=${tp('bubble.download_title')}
                        @click=${(e) => e.stopPropagation()}
                    >${_svgImageDownload}</a>
                </div>
                ${filename ? html`<div class="file-image-caption">${filename}</div>` : ''}
            </div>
        `;
    }
    if (content.type === 'file/document') {
        const { file_id: fileId, filename, mime_type: mimeType, size } = content.data ?? {};
        if (typeof fileId !== 'string') throw new Error(tp('bubble.err_file_document'));
        const downloadUrl = `/sync/api/v1/files/download/${fileId}`;
        const label = filename ?? tp('bubble.file_fallback');
        const sizeLabel = typeof size === 'number' ? _formatFileSize(size, tp) : '';
        const nameForIcon = typeof filename === 'string' ? filename : '';
        const mimeForIcon = typeof mimeType === 'string' ? mimeType : '';
        const fileIconKey = host.icon.resolveFileIconKey(nameForIcon, mimeForIcon);
        return html`
            <a class="file-card" href=${downloadUrl} download=${label} target="_blank">
                <div class="file-card-icon">
                    <platform-icon file-icon name=${fileIconKey} size="22"></platform-icon>
                </div>
                <div class="file-card-info">
                    <span class="file-card-name">${label}</span>
                    ${sizeLabel ? html`<span class="file-card-size">${sizeLabel}</span>` : ''}
                </div>
                <div class="file-card-dl" title=${tp('bubble.download_title')}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                        <path d="M12 3v13M5 15l7 7 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M3 21h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                    </svg>
                </div>
            </a>
        `;
    }
    if (content.type === 'file/audio') {
        const {
            file_id: fileId,
            filename,
            duration_ms: durationMs,
            waveform,
            transcription_status: transcriptionStatus,
            transcription_text: transcriptionText,
            transcription_error: transcriptionError,
        } = content.data ?? {};
        if (typeof fileId !== 'string' || fileId === '') {
            throw new Error(tp('bubble.err_file_audio'));
        }
        const src = `/sync/api/v1/files/download/${fileId}`;
        const safeDurationMs = typeof durationMs === 'number' && Number.isFinite(durationMs) ? durationMs : 0;
        const safeWaveform = Array.isArray(waveform) ? waveform : null;
        const safeStatus = typeof transcriptionStatus === 'string' && transcriptionStatus !== ''
            ? transcriptionStatus
            : 'idle';
        const safeText = typeof transcriptionText === 'string' ? transcriptionText : '';
        const safeError = typeof transcriptionError === 'string' ? transcriptionError : '';
        return html`
            <platform-audio-message-player
                .src=${src}
                .fileName=${typeof filename === 'string' ? filename : ''}
                .durationMs=${safeDurationMs}
                .waveform=${safeWaveform}
                .transcriptionStatus=${safeStatus}
                .transcriptionText=${safeText}
                .transcriptionError=${safeError}
                @request-transcription=${(e) => {
                    e.stopPropagation();
                    host._requestAudioTranscription();
                }}
            ></platform-audio-message-player>
        `;
    }
    if (content.type === 'file/video') {
        const {
            file_id: fileId,
            filename,
            transcription_status: transcriptionStatus,
            transcription_text: transcriptionText,
            transcription_error: transcriptionError,
        } = content.data ?? {};
        if (typeof fileId !== 'string' || fileId === '') {
            throw new Error(tp('bubble.err_file_video'));
        }
        const src = `/sync/api/v1/files/download/${fileId}`;
        const label = typeof filename === 'string' && filename !== '' ? filename : tp('bubble.file_fallback');
        const safeStatus = typeof transcriptionStatus === 'string' && transcriptionStatus !== ''
            ? transcriptionStatus
            : 'idle';
        const safeText = typeof transcriptionText === 'string' ? transcriptionText : '';
        const safeError = typeof transcriptionError === 'string' ? transcriptionError : '';
        const canRequest = safeStatus === 'idle' || safeStatus === 'failed';
        return html`
            <div class="video-attachment">
                <video class="video-attachment-player" controls preload="metadata" src=${src}></video>
                <div class="video-attachment-toolbar">
                    <a
                        class="transcribe-btn"
                        href=${src}
                        download=${label}
                        target="_blank"
                        @click=${(e) => e.stopPropagation()}
                    >${tp('bubble.download_title')}</a>
                    ${canRequest
                        ? html`
                            <button
                                type="button"
                                class="transcribe-btn"
                                @click=${(e) => {
                                    e.stopPropagation();
                                    host._requestVideoTranscription();
                                }}
                            >${tp('bubble.transcribe_video')}</button>
                        `
                        : ''}
                </div>
                ${safeStatus === 'processing'
                    ? html`<div class="transcribe-hint">${tp('bubble.transcribe_processing')}</div>`
                    : ''}
                ${safeError !== '' ? html`<div class="transcribe-err">${safeError}</div>` : ''}
                ${safeText !== '' ? html`<div class="msg-text video-transcript">${safeText}</div>` : ''}
            </div>
        `;
    }
    if (content.type === 'call/boundary') {
        const callId = content.data?.call_id;
        const phase = content.data?.phase;
        if (typeof callId !== 'string' || callId === '') {
            throw new Error(tp('bubble.err_call_boundary'));
        }
        if (phase !== 'started' && phase !== 'ended') {
            throw new Error(tp('bubble.err_call_boundary'));
        }
        const label = phase === 'started'
            ? tp('bubble.call_boundary_started')
            : tp('bubble.call_boundary_ended');
        if (phase === 'started') {
            const showJoin = _callBoundaryShowJoinButton(host, callId);
            return html`
                <div class="call-boundary call-boundary--started" role="group" aria-label=${label}>
                    ${showJoin
                        ? html`
                            <button
                                type="button"
                                class="call-boundary-join-btn"
                                title=${tp('bubble.call_boundary_join_title')}
                                aria-label=${tp('bubble.call_boundary_join_title')}
                                @click=${(e) => {
                                    e.stopPropagation();
                                    host._joinCallFromBoundary(callId);
                                }}
                            >
                                ${_svgCallBoundaryJoin}
                                ${tp('bubble.call_boundary_join')}
                            </button>
                        `
                        : html`<span class="call-boundary-started-note">${label}</span>`}
                </div>
            `;
        }
        return html`
            <div class="call-boundary call-boundary--ended" role="group" aria-label=${label}>
                <div class="call-boundary-icon" title=${label}>
                    <platform-icon name="phone-ended" size="20" filled aria-hidden="true"></platform-icon>
                </div>
                <button
                    type="button"
                    class="call-boundary-transcribe"
                    title=${tp('bubble.transcribe_meeting')}
                    aria-label=${tp('bubble.transcribe_meeting')}
                    @click=${(e) => {
                        e.stopPropagation();
                        host._requestCallTranscribe();
                    }}
                >
                    <platform-icon name="doc-detail" size="18" aria-hidden="true"></platform-icon>
                </button>
            </div>
        `;
    }
    if (content.type === 'git/reference') {
        const gitRefId = content.data?.git_ref_id;
        if (typeof gitRefId !== 'string') throw new Error(tp('bubble.err_git_ref'));
        return html`<div class="content-ref">Git: ${gitRefId}</div>`;
    }
    if (content.type === 'custom_tool_response') {
        const toolName = content.data?.tool_name;
        if (typeof toolName !== 'string') throw new Error(tp('bubble.err_tool_response'));
        return html`<div class="content-ref">Tool: ${toolName}</div>`;
    }
    throw new Error(tp('bubble.err_content_type', { type: content.type }));
}

const checkSingle = html`
    <svg class="check-icon" viewBox="0 0 16 10" width="14" height="9" fill="none" aria-hidden="true">
        <path d="M1.5 5L6 9L14.5 1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;

const checkDouble = html`
    <svg class="check-icon check-icon--read" viewBox="0 0 21 10" width="18" height="9" fill="none" aria-hidden="true">
        <path d="M1 5L5.5 9L14 1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M7 5L11.5 9L20 1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;

export class MessageBubble extends PlatformElement {
    static properties = {
        msg: { type: Object },
        isOwn: { type: Boolean },
        canFocusThread: { type: Boolean },
        channelId: { type: String },
        activeCallOverlay: { type: Object },
        pinnedMessageIds: { type: Array },
        selectionMode: { type: Boolean },
        selected: { type: Boolean },
        flashActive: { type: Boolean },
        flashSeq: { type: Number },
        deleting: { type: Boolean },
        peerReadAt: { type: String },
        channelType: { type: String },
        _profileOpen: { state: true },
        _profileUser: { state: true },
        _menuOpen: { state: true },
        _menuX: { state: true },
        _menuY: { state: true },
        _pressHoldVisual: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        css`
            :host {
                display: block;
            }

            .bubble-row {
                display: flex;
                align-items: flex-end;
                gap: var(--space-2);
            }

            .bubble-row.own {
                justify-content: flex-end;
            }

            .bubble-row.other {
                justify-content: flex-start;
            }

            .bubble-row.bubble-row--press-hold {
                -webkit-user-select: none;
                user-select: none;
            }

            .bubble-row.bubble-row--press-hold .bubble {
                transform: scale(0.97);
                box-shadow: inset 0 3px 10px rgba(0, 0, 0, 0.14);
            }

            .bubble-row.flash-target .bubble {
                animation: bubble-flash-ring 2.6s ease-out;
            }

            @keyframes bubble-flash-ring {
                0% {
                    box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.45);
                }
                35% {
                    box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.22);
                }
                100% {
                    box-shadow: 0 0 0 0 transparent;
                }
            }

            .bubble-row--destroying {
                pointer-events: none;
            }

            .bubble-row--destroying .bubble {
                animation: message-destroy-bubble 0.58s cubic-bezier(0.4, 0, 0.2, 1) forwards;
                will-change: transform, opacity, filter;
            }

            .bubble-row--destroying .avatar-slot {
                animation: message-destroy-avatar 0.58s cubic-bezier(0.4, 0, 0.2, 1) forwards;
                will-change: transform, opacity, filter;
            }

            .bubble-row--destroying .select-wrap {
                opacity: 0;
                transition: opacity 0.15s ease;
            }

            @keyframes message-destroy-bubble {
                0% {
                    opacity: 1;
                    transform: translateY(0) scale(1) rotate(0deg);
                    filter: blur(0) brightness(1);
                }
                22% {
                    opacity: 0.94;
                    transform: translateY(2px) scale(0.985) rotate(-0.4deg);
                    filter: blur(0.5px) brightness(1.02);
                }
                100% {
                    opacity: 0;
                    transform: translateY(18px) scale(0.74) rotate(1.4deg);
                    filter: blur(14px) brightness(1.45);
                }
            }

            @keyframes message-destroy-avatar {
                0% {
                    opacity: 1;
                    transform: scale(1);
                    filter: blur(0);
                }
                100% {
                    opacity: 0;
                    transform: scale(0.82);
                    filter: blur(10px);
                }
            }

            .avatar-slot {
                flex: 0 0 auto;
                width: 36px;
                height: 36px;
                border-radius: 50%;
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
            }

            .avatar-slot button {
                width: 100%;
                height: 100%;
                padding: 0;
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
            }

            .avatar-img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .avatar-initials {
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 13px;
                font-weight: var(--font-semibold);
                color: #fff;
                letter-spacing: 0.02em;
                user-select: none;
            }

            .bubble {
                position: relative;
                min-width: 0;
                width: fit-content;
                max-width: min(720px, 90%);
                border-radius: var(--radius-2xl);
                padding: var(--space-2) var(--space-3);
                border: 1px solid;
                transition: transform 0.14s ease-out, box-shadow 0.14s ease-out;
            }

            .bubble--forwarded .bubble-header {
                padding-left: 18px;
            }

            .forwarded-corner {
                position: absolute;
                left: 8px;
                top: 8px;
                z-index: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                opacity: 0.92;
                line-height: 1;
            }

            .bubble-row.other .bubble {
                max-width: min(720px, calc(90% - 44px));
            }

            .bubble.own {
                border-color: rgba(16, 185, 129, 0.35);
                background: rgba(16, 185, 129, 0.16);
            }

            .bubble.own.bubble--media {
                border-color: rgba(16, 185, 129, 0.35);
                background: rgba(16, 185, 129, 0.16);
            }

            :host-context([data-theme="dark"]) .bubble.own.bubble--media {
                border-color: rgba(100, 116, 139, 0.42);
                background: rgba(51, 65, 85, 0.3);
            }

            /* Without this, flex (bubble-contents + time) with min-width:0 shrinks the audio player to a pill. */
            .bubble.bubble--media {
                min-width: min(288px, 100%);
            }

            .bubble.bubble--media .bubble-contents {
                flex: 1 1 auto;
                min-width: min(236px, calc(100% - 52px));
            }

            .bubble.bubble--media platform-audio-message-player {
                display: block;
                min-width: 220px;
                max-width: 100%;
            }

            /* Own-bubble mint background: default player colors blend in; wave and time need darker tokens. */
            .bubble.own.bubble--media platform-audio-message-player {
                --platform-audio-bar-inactive: rgba(4, 52, 34, 0.58);
                --platform-audio-bar-active: rgba(2, 36, 24, 0.98);
                --platform-audio-time: rgba(2, 36, 24, 0.92);
                --platform-audio-transcribe-border: rgba(2, 36, 24, 0.45);
                --platform-audio-transcribe-bg: rgba(255, 255, 255, 0.72);
                --platform-audio-transcribe-fg: rgba(2, 36, 24, 0.92);
                --platform-audio-transcription-text: rgba(2, 36, 24, 0.92);
                --platform-audio-range-accent: rgb(4, 92, 58);
            }

            :host-context([data-theme="dark"]) .bubble.own.bubble--media platform-audio-message-player {
                --platform-audio-bar-inactive: rgba(226, 232, 240, 0.42);
                --platform-audio-bar-active: rgba(248, 250, 252, 0.95);
                --platform-audio-time: rgba(241, 245, 249, 0.92);
                --platform-audio-transcribe-border: rgba(226, 232, 240, 0.35);
                --platform-audio-transcribe-bg: rgba(30, 41, 59, 0.55);
                --platform-audio-transcribe-fg: rgba(241, 245, 249, 0.92);
                --platform-audio-transcription-text: rgba(241, 245, 249, 0.9);
                --platform-audio-range-accent: rgb(52, 211, 153);
            }

            .video-attachment {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: min(100%, 320px);
                max-width: min(720px, 100%);
            }

            .video-attachment-player {
                width: 100%;
                max-height: 360px;
                border-radius: var(--radius-lg);
                background: #000;
            }

            .video-attachment-toolbar {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
            }

            .transcribe-btn {
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .transcribe-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .transcribe-hint,
            .transcribe-err {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .transcribe-err {
                color: rgb(239, 68, 68);
            }

            .call-boundary {
                display: inline-flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-2);
                padding: 0;
                margin: 0;
                border: none;
                background: transparent;
                max-width: 100%;
                box-sizing: border-box;
            }

            .call-boundary-started-note {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .call-boundary-join-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                min-height: 30px;
                padding: 4px 12px;
                box-sizing: border-box;
                border-radius: var(--radius-md);
                border: 1px solid rgba(22, 163, 74, 0.45);
                background: rgba(22, 163, 74, 0.1);
                color: #15803d;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                cursor: pointer;
                font-family: inherit;
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
            }

            .call-boundary-join-btn:hover {
                background: rgba(22, 163, 74, 0.16);
                border-color: rgba(21, 128, 61, 0.55);
                color: #166534;
            }

            .bubble.other .call-boundary-join-btn {
                border-color: rgba(3, 105, 161, 0.4);
                background: rgba(56, 189, 248, 0.12);
                color: rgb(2, 92, 145);
            }

            .bubble.other .call-boundary-join-btn:hover {
                border-color: rgba(2, 92, 145, 0.55);
                background: rgba(56, 189, 248, 0.2);
                color: rgb(1, 75, 115);
            }

            .call-boundary-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                border-radius: var(--radius-full);
                flex-shrink: 0;
                box-sizing: border-box;
            }

            .bubble.own .call-boundary--ended .call-boundary-icon {
                background: rgba(255, 255, 255, 0.36);
                color: rgb(4, 85, 62);
            }

            .bubble.other .call-boundary--ended .call-boundary-icon {
                background: rgba(255, 255, 255, 0.42);
                color: rgb(2, 92, 145);
            }

            .call-boundary-transcribe {
                display: inline-flex;
                width: 36px;
                height: 36px;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                border: 1px solid rgba(255, 255, 255, 0.45);
                background: rgba(255, 255, 255, 0.22);
                cursor: pointer;
                padding: 0;
                flex-shrink: 0;
                box-sizing: border-box;
                transition: background var(--duration-fast), border-color var(--duration-fast);
            }

            .bubble.own .call-boundary-transcribe {
                color: rgb(6, 95, 70);
            }

            .bubble.other .call-boundary-transcribe {
                color: rgb(3, 105, 161);
            }

            .call-boundary-transcribe:hover {
                background: rgba(255, 255, 255, 0.38);
                border-color: rgba(255, 255, 255, 0.58);
            }

            .call-boundary-transcribe:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }

            .bubble.bubble--call-boundary {
                padding: var(--space-2) var(--space-3);
            }

            .bubble.bubble--call-boundary .bubble-body {
                align-items: center;
            }

            .bubble.bubble--call-boundary .contents-inner {
                gap: 0;
            }

            .bubble.other {
                border-color: rgba(56, 189, 248, 0.28);
                background: rgba(147, 197, 253, 0.35);
            }

            .bubble-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-1);
            }

            .bubble-header-end {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .pin-mark {
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                opacity: 0.9;
            }

            .sender-info {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .bubble-body {
                display: flex;
                align-items: flex-end;
                gap: var(--space-1);
            }

            .bubble-contents {
                flex: 0 1 auto;
                min-width: 0;
            }

            .bubble-time {
                flex: 0 0 auto;
                align-self: flex-end;
                font-size: 11px;
                line-height: 1.25;
                letter-spacing: 0.02em;
                white-space: nowrap;
                padding-bottom: 1px;
            }

            .bubble.other .bubble-time {
                color: var(--text-tertiary);
            }

            .bubble.own .bubble-time {
                color: rgba(6, 95, 70, 0.8);
            }

            .sender-btn {
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                padding: 0;
                text-decoration: none;
            }

            .sender-btn:hover {
                text-decoration: underline;
                text-underline-offset: 4px;
            }

            .thread-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
                padding: 2px 8px;
                transition: all var(--duration-fast);
                flex-shrink: 0;
            }

            .thread-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .bubble-contents .contents-inner {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .msg-text {
                font-size: var(--text-base);
                color: var(--text-primary);
                /* pre-wrap in flex column inflates height; pre-line keeps line breaks */
                white-space: pre-line;
                overflow-wrap: anywhere;
                word-break: normal;
                line-height: 1.45;
            }

            .msg-text .msg-mention {
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .msg-text .msg-mention--interactive {
                cursor: pointer;
            }

            .msg-text .msg-mention--interactive:hover {
                text-decoration: underline;
                text-underline-offset: 3px;
            }

            .code-block {
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: rgba(0, 0, 0, 0.3);
                padding: var(--space-3);
                backdrop-filter: blur(var(--glass-blur-medium));
            }

            .code-lang {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }

            .code-source {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                overflow: auto;
                margin: 0;
            }

            .content-ref {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .file-image-wrap {
                display: flex;
                flex-direction: column;
                gap: 4px;
                max-width: 320px;
            }

            .file-image-frame {
                position: relative;
                display: inline-block;
                max-width: 100%;
                line-height: 0;
            }

            .file-image {
                max-width: 100%;
                max-height: 400px;
                border-radius: var(--radius-lg);
                cursor: pointer;
                display: block;
                object-fit: contain;
            }

            .file-image-dl {
                position: absolute;
                top: 8px;
                right: 8px;
                z-index: 2;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border-radius: var(--radius-md);
                background: rgba(0, 0, 0, 0.48);
                color: #fff;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
                text-decoration: none;
                transition: background var(--duration-fast), transform var(--duration-fast);
            }

            .file-image-dl:hover {
                background: rgba(0, 0, 0, 0.65);
            }

            .file-image-dl:active {
                transform: scale(0.96);
            }

            .file-image-caption {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .file-missing {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-1) var(--space-2);
                background: var(--glass-solid-subtle);
                max-width: 320px;
                overflow-wrap: anywhere;
            }

            .file-card {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                text-decoration: none;
                color: var(--text-primary);
                max-width: 280px;
                transition: background var(--duration-fast);
            }

            .file-card:hover {
                background: var(--glass-solid-medium);
            }

            .file-card-icon {
                flex-shrink: 0;
                color: var(--text-secondary);
                display: flex;
                align-items: center;
            }

            .file-card-info {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .file-card-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .file-card-size {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .file-card-dl {
                flex-shrink: 0;
                color: var(--text-secondary);
                display: flex;
                align-items: center;
            }

            .bubble-time.status-pending {
                color: var(--text-tertiary);
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }

            .bubble-time.status-failed {
                color: var(--error);
            }

            .bubble-time.own-time {
                display: inline-flex;
                align-items: center;
                gap: 3px;
            }

            .sending-spinner {
                display: inline-block;
                width: 10px;
                height: 10px;
                border: 1.5px solid currentColor;
                border-top-color: transparent;
                border-radius: 50%;
                animation: spin-sending 0.7s linear infinite;
                flex-shrink: 0;
            }

            @keyframes spin-sending {
                to { transform: rotate(360deg); }
            }

            .check-icon {
                color: rgba(6, 95, 70, 0.65);
                flex-shrink: 0;
                display: inline-block;
                vertical-align: middle;
            }

            .check-icon--read {
                color: rgb(5, 150, 105);
            }

            .reply-quote {
                display: block;
                width: 100%;
                margin: 0 0 var(--space-1) 0;
                padding: var(--space-1) var(--space-2);
                border: none;
                border-radius: var(--radius-md);
                text-align: left;
                cursor: pointer;
                font: inherit;
                max-width: 100%;
                box-sizing: border-box;
                border-left: 4px solid var(--text-tertiary);
                background: var(--glass-solid-subtle);
            }

            .reply-quote--parent-own {
                border-left-color: rgb(5, 150, 105);
                background: rgba(16, 185, 129, 0.26);
            }

            .reply-quote--parent-other {
                border-left-color: rgb(2, 132, 199);
                background: rgba(147, 197, 253, 0.52);
            }

            .reply-quote--unknown {
                border-left-color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
            }

            .reply-quote:hover {
                filter: brightness(0.97);
            }

            .reply-quote:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }

            .reply-quote__author {
                display: block;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                margin-bottom: 1px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .reply-quote--parent-own .reply-quote__author {
                color: rgb(4, 120, 87);
            }

            .reply-quote--parent-other .reply-quote__author {
                color: rgb(3, 105, 161);
            }

            .reply-quote--unknown .reply-quote__author {
                color: var(--text-secondary);
            }

            .reply-quote__text {
                display: block;
                font-size: var(--text-xs);
                color: var(--text-primary);
                line-height: 1.35;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .edited-badge {
                font-size: 10px;
                color: var(--text-tertiary);
            }

            .reactions-row {
                display: flex;
                flex-wrap: wrap;
                gap: 4px;
                margin-top: var(--space-1);
            }

            .reaction-chip {
                font-size: 13px;
                padding: 2px 6px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }

            .select-wrap {
                flex-shrink: 0;
                align-self: flex-start;
                padding-top: 4px;
            }

            .select-cb {
                width: 18px;
                height: 18px;
            }
        `
    ];

    constructor() {
        super();
        this.msg = null;
        this.isOwn = false;
        this.canFocusThread = false;
        this.channelId = null;
        this.pinnedMessageIds = [];
        this.selectionMode = false;
        this.selected = false;
        this.flashActive = false;
        this.flashSeq = 0;
        this.deleting = false;
        this.peerReadAt = null;
        this.channelType = null;
        this._avatarRetry = createAvatarRetry(() => this.requestUpdate());
        this._profileOpen = false;
        this._profileUser = null;
        this._menuOpen = false;
        this._menuX = 0;
        this._menuY = 0;
        this._pressHoldVisual = false;
        /** @type {ReturnType<typeof setTimeout> | null} */
        this._longPressTimer = null;
        /** @type {number | null} */
        this._pressPointerId = null;
        /** @type {AbortController | null} */
        this._abortLongPress = null;
        this._pressStartX = 0;
        this._pressStartY = 0;
        this._lastPointerX = 0;
        this._lastPointerY = 0;
        this._suppressNextContextMenu = false;
        /** @type {(() => void) | null} */
        this._unsubCompanyMembers = null;
        /** @type {unknown} */
        this._companyMembersListRef = null;
        /** @type {(() => void) | null} */
        this._i18nUnsub = null;
    }

    _tp(key, params) {
        return this.i18n.t(key, params ?? {});
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._companyMembersListRef = SyncStore.state.companyMembers?.list;
        this._unsubCompanyMembers = SyncStore.subscribe(() => {
            const next = SyncStore.state.companyMembers?.list;
            if (next !== this._companyMembersListRef) {
                this._companyMembersListRef = next;
                this.requestUpdate();
            }
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._i18nUnsub?.();
        this._i18nUnsub = null;
        this._avatarRetry.cancel();
        this._unsubCompanyMembers?.();
        this._unsubCompanyMembers = null;
        this._endLongPressGesture();
    }

    _focusThread() {
        if (this.msg?.thread_id) {
            this.emit('focus-thread', { threadId: this.msg.thread_id });
        }
    }

    updated(changedProperties) {
        super.updated?.(changedProperties);
        if (!this.flashActive) return;
        const prevSeq = changedProperties.get('flashSeq');
        if (prevSeq === undefined || prevSeq === 0) return;
        if (prevSeq === this.flashSeq) return;
        const bubble = this.shadowRoot?.querySelector('.bubble-row.flash-target .bubble');
        if (!bubble) return;
        bubble.style.animation = 'none';
        void bubble.offsetWidth;
        bubble.style.animation = '';
    }


    _renderAvatarSlot() {
        const sender = this.msg.sender;
        if (!sender || typeof sender.user_id !== 'string') {
            throw new Error(this._tp('bubble.err_no_sender'));
        }
        const defaultUser = this._tp('composer.default_user_short');
        const shortName = toShortUsername(sender.display_name ?? '', defaultUser);
        const initials = initialsForAvatar(sender.display_name ?? '', defaultUser);
        const hue = hueFromUserId(sender.user_id);
        const initialsStyle = `background: hsl(${hue} 48% 42%);`;
        const originalUrl = sender.avatar_url ?? null;
        const src = this._avatarRetry.currentSrc(originalUrl);
        const face = src
            ? html`
                <img class="avatar-img" src=${src} alt=${shortName}
                    @load=${() => this._avatarRetry.onLoad()}
                    @error=${() => this._avatarRetry.onError(originalUrl)} />
            `
            : html`
                <span class="avatar-initials" style=${initialsStyle}>${initials}</span>
            `;

        return html`
            <div class="avatar-slot">
                <button
                    type="button"
                    @click=${() => {
                        this._profileUser = sender;
                        this._profileOpen = true;
                    }}
                    aria-label=${this._tp('bubble.profile_aria', { name: shortName })}
                >
                    ${face}
                </button>
            </div>
        `;
    }

    _clearLongPressTimer() {
        if (this._longPressTimer !== null) {
            clearTimeout(this._longPressTimer);
            this._longPressTimer = null;
        }
    }

    _endLongPressGesture() {
        this._clearLongPressTimer();
        if (this._abortLongPress !== null) {
            this._abortLongPress.abort();
            this._abortLongPress = null;
        }
        this._pressPointerId = null;
        this._pressHoldVisual = false;
    }

    _openMentionProfile(userId) {
        if (typeof userId !== 'string' || userId === '') {
            throw new Error(this._tp('bubble.err_mention_user'));
        }
        const members = SyncStore.state.companyMembers?.list ?? [];
        const cm = members.find(m => m.user_id === userId);
        this._profileUser = {
            user_id: userId,
            display_name: typeof cm?.name === 'string' && cm.name.trim() !== ''
                ? cm.name.trim()
                : mentionDisplayLabel(userId, members),
            avatar_url: typeof cm?.avatar_url === 'string' && cm.avatar_url !== '' ? cm.avatar_url : null,
        };
        this._profileOpen = true;
    }

    _onProfileClose() {
        this._profileOpen = false;
        this._profileUser = null;
    }

    _openMessageMenuAt(clientX, clientY) {
        this._menuX = clientX;
        this._menuY = clientY;
        this._menuOpen = true;
    }

    _onBubblePointerDown(e) {
        if (this.selectionMode || this.deleting) return;
        if (e.pointerType === 'mouse') return;

        this._endLongPressGesture();

        this._pressPointerId = e.pointerId;
        this._pressStartX = e.clientX;
        this._pressStartY = e.clientY;
        this._lastPointerX = e.clientX;
        this._lastPointerY = e.clientY;
        this._pressHoldVisual = true;

        this._abortLongPress = new AbortController();
        const signal = this._abortLongPress.signal;
        const opts = { signal, capture: true };

        const onMove = (ev) => {
            if (ev.pointerId !== this._pressPointerId) return;
            this._lastPointerX = ev.clientX;
            this._lastPointerY = ev.clientY;
            const dx = ev.clientX - this._pressStartX;
            const dy = ev.clientY - this._pressStartY;
            if (dx * dx + dy * dy > LONG_PRESS_MOVE_CANCEL_PX * LONG_PRESS_MOVE_CANCEL_PX) {
                this._endLongPressGesture();
            }
        };

        const onEnd = (ev) => {
            if (ev.pointerId !== this._pressPointerId) return;
            this._endLongPressGesture();
        };

        document.addEventListener('pointermove', onMove, opts);
        document.addEventListener('pointerup', onEnd, opts);
        document.addEventListener('pointercancel', onEnd, opts);

        this._longPressTimer = window.setTimeout(() => {
            this._longPressTimer = null;
            this._suppressNextContextMenu = true;
            const x = this._lastPointerX;
            const y = this._lastPointerY;
            this._endLongPressGesture();
            this._openMessageMenuAt(x, y);
        }, LONG_PRESS_MS);
    }

    _onContextMenu(e) {
        e.preventDefault();
        if (this._suppressNextContextMenu) {
            this._suppressNextContextMenu = false;
            return;
        }
        this._openMessageMenuAt(e.clientX, e.clientY);
    }

    async _onMenuAction(e) {
        this._menuOpen = false;
        const { kind, emoji } = e.detail;
        const syncApi = this.services.get('syncApi');
        const { msg, channelId } = this;
        if (!msg?.id) throw new Error(this._tp('bubble.err_no_message'));
        if (!channelId) throw new Error(this._tp('bubble.err_no_channel'));

        if (kind === 'reply') {
            SyncStore.setReplyToMessage(msg);
            return;
        }
        if (kind === 'copy') {
            const text = extractPlainText(msg);
            if (text === '') throw new Error(this._tp('bubble.err_no_copy_text'));
            await copyTextToClipboard(text);
            return;
        }
        if (kind === 'translate') {
            const text = extractPlainText(msg);
            const q = text === '' ? '' : `&q=${encodeURIComponent(text)}`;
            globalThis.open(`https://translate.google.com/?sl=auto&tl=ru${q}`, '_blank');
            return;
        }
        if (kind === 'edit') {
            SyncStore.setEditMessage(msg);
            return;
        }
        if (kind === 'pin') {
            const pinned = this.pinnedMessageIds ?? [];
            const isPinned = pinned.includes(msg.id);
            await syncApi.pinMessage(channelId, msg.id, isPinned ? 'remove' : 'add');
            return;
        }
        if (kind === 'forward') {
            SyncStore.setForwardModal(true, msg);
            return;
        }
        if (kind === 'select') {
            SyncStore.setSelectionMode(true);
            SyncStore.toggleMessageSelection(msg.id);
            return;
        }
        if (kind === 'delete') {
            await syncApi.deleteMessage(channelId, msg.id);
            return;
        }
        if (kind === 'react') {
            if (typeof emoji !== 'string' || emoji.trim() === '') {
                throw new Error(this._tp('bubble.err_emoji'));
            }
            await syncApi.reactMessage(channelId, msg.id, emoji);
        }
    }

    _isPinned() {
        const id = this.msg?.id;
        const pins = this.pinnedMessageIds;
        if (!id || !Array.isArray(pins)) return false;
        return pins.includes(id);
    }

    _forwardedMeta() {
        const f = this.msg?.forwarded_from;
        if (!f || typeof f.channel_id !== 'string' || f.channel_id === '') {
            return null;
        }
        const nm = typeof f.channel_name === 'string' ? f.channel_name.trim() : '';
        const label = nm !== '' ? nm : f.channel_id;
        return { tip: this._tp('bubble.forwarded_from', { label }) };
    }

    _onReplyPreviewClick(e) {
        e.stopPropagation();
        e.preventDefault();
        const pid = this.msg?.parent_message_id;
        if (typeof pid !== 'string' || pid === '') {
            throw new Error(this._tp('bubble.err_parent_id'));
        }
        this.emit('scroll-to-message', { messageId: pid });
    }

    async _requestAudioTranscription() {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            throw new Error(this._tp('bubble.err_channel_transcribe'));
        }
        if (typeof this.msg?.id !== 'string' || this.msg.id === '') {
            throw new Error(this._tp('bubble.err_message_transcribe'));
        }
        const syncApi = this.services.get('syncApi');
        const updated = await syncApi.transcribeMessage(this.channelId, this.msg.id);
        if (updated && typeof updated === 'object' && typeof updated.id === 'string') {
            SyncStore.upsertMessage(updated);
        }
    }

    async _requestVideoTranscription() {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            throw new Error(this._tp('bubble.err_channel_transcribe'));
        }
        if (typeof this.msg?.id !== 'string' || this.msg.id === '') {
            throw new Error(this._tp('bubble.err_message_transcribe'));
        }
        const syncApi = this.services.get('syncApi');
        const updated = await syncApi.transcribeVideoMessage(this.channelId, this.msg.id);
        if (updated && typeof updated === 'object' && typeof updated.id === 'string') {
            SyncStore.upsertMessage(updated);
        }
    }

    async _requestCallTranscribe() {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            throw new Error(this._tp('bubble.err_channel_transcribe'));
        }
        const callId = this.msg?.call_id;
        if (typeof callId !== 'string' || callId === '') {
            throw new Error(this._tp('bubble.err_call_id_transcribe'));
        }
        const syncApi = this.services.get('syncApi');
        await syncApi.transcribeCallSession(this.channelId, callId);
    }

    _joinCallFromBoundary(callId) {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            throw new Error(this._tp('bubble.err_no_channel'));
        }
        if (typeof callId !== 'string' || callId === '') {
            throw new Error(this._tp('bubble.err_call_id_transcribe'));
        }
        this.dispatchEvent(new CustomEvent('join-call-from-boundary', {
            bubbles: true,
            composed: true,
            detail: { channelId: this.channelId, callId },
        }));
    }

    _parentPreview() {
        const pid = this.msg?.parent_message_id;
        if (!pid) return null;
        const all = SyncStore.getDisplayMessages();
        const p = all.find(m => m.id === pid);
        const myId = this.auth?.user?.id;
        const parentIsOwn =
            typeof myId === 'string' &&
            p !== undefined &&
            senderUserId(p.sender) === myId;
        const quoteClass = !p
            ? 'reply-quote--unknown'
            : parentIsOwn
              ? 'reply-quote--parent-own'
              : 'reply-quote--parent-other';
        const defaultUser = this._tp('composer.default_user_short');
        const who = p ? toShortUsername(p.sender?.display_name ?? '', defaultUser) : this._tp('bubble.default_message');
        const membersList = SyncStore.state.companyMembers?.list;
        const snippetRaw = p
            ? plainTextSnippetWithMentionLabels(extractPlainText(p), membersList, 160)
            : '';
        const snippet = snippetRaw !== '' ? snippetRaw : this._tp('bubble.default_message');

        return html`
            <button type="button" class="reply-quote ${quoteClass}" @click=${this._onReplyPreviewClick}>
                <span class="reply-quote__author">${who}</span>
                <span class="reply-quote__text">${snippet}</span>
            </button>
        `;
    }

    _reactionsLine() {
        const rx = this.msg?.reactions;
        if (!Array.isArray(rx) || rx.length === 0) return null;
        const groups = new Map();
        for (const r of rx) {
            if (!r?.emoji) continue;
            const n = (groups.get(r.emoji) ?? 0) + 1;
            groups.set(r.emoji, n);
        }
        const chips = [...groups.entries()].map(([em, n]) => html`
            <span class="reaction-chip">${em}${n > 1 ? ` ${n}` : ''}</span>
        `);
        return html`<div class="reactions-row">${chips}</div>`;
    }

    _renderTimeMeta() {
        const { msg, isOwn, peerReadAt, channelType } = this;
        const { status, sent_at } = msg;

        if (status === 'failed') {
            return html`<span class="bubble-time status-failed">${this._tp('bubble.status_error')}</span>`;
        }

        const timeStr = formatMessageTime(sent_at, this.i18n.getCurrentLocale());

        if (!isOwn) {
            return html`<span class="bubble-time">${timeStr}</span>`;
        }

        if (status === 'pending') {
            return html`
                <span class="bubble-time own-time">
                    ${timeStr}
                    <span class="sending-spinner"></span>
                </span>
            `;
        }

        const isRead = channelType === 'direct'
            && typeof peerReadAt === 'string'
            && peerReadAt !== ''
            && new Date(sent_at) <= new Date(peerReadAt);

        return html`
            <span class="bubble-time own-time">
                ${timeStr}
                ${isRead ? checkDouble : checkSingle}
            </span>
        `;
    }

    render() {
        if (!this.msg) return html``;
        const { msg, isOwn, canFocusThread, flashActive, deleting } = this;
        const sorted = [...(msg.contents ?? [])].sort((a, b) => a.order - b.order);
        const isCompactMediaBubble = sorted.length === 1
            && (sorted[0]?.type === 'file/audio' || sorted[0]?.type === 'file/video');
        const isCallBoundaryOnly = sorted.length === 1 && sorted[0]?.type === 'call/boundary';
        const fwdMeta = this._forwardedMeta();
        const hasEdited = Boolean(msg.edited_at);
        const hasHeaderEnd = this._isPinned() || canFocusThread;
        const showBubbleHeader = !isOwn || hasEdited || hasHeaderEnd;

        return html`
            <div
                class="bubble-row ${isOwn ? 'own' : 'other'} ${flashActive ? 'flash-target' : ''} ${deleting ? 'bubble-row--destroying' : ''} ${this._pressHoldVisual ? 'bubble-row--press-hold' : ''}"
                data-message-id=${msg.id}
                @contextmenu=${this._onContextMenu}
                @pointerdown=${this._onBubblePointerDown}
            >
                ${this.selectionMode ? html`
                    <div class="select-wrap">
                        <input
                            type="checkbox"
                            class="select-cb"
                            .checked=${this.selected}
                            @change=${() => SyncStore.toggleMessageSelection(msg.id)}
                        />
                    </div>
                ` : ''}
                ${isOwn ? '' : this._renderAvatarSlot()}
                <div class="bubble ${isOwn ? 'own' : 'other'} ${fwdMeta ? 'bubble--forwarded' : ''} ${isCompactMediaBubble ? 'bubble--media' : ''} ${isCallBoundaryOnly ? 'bubble--call-boundary' : ''}">
                    ${fwdMeta ? html`
                        <span class="forwarded-corner" title=${fwdMeta.tip}>
                            <platform-icon name="share" size="12"></platform-icon>
                        </span>
                    ` : ''}
                    ${showBubbleHeader ? html`
                        <div class="bubble-header">
                            <div class="sender-info">
                                ${!isOwn ? html`
                                    <button
                                        class="sender-btn"
                                        @click=${() => {
                                            this._profileUser = msg.sender;
                                            this._profileOpen = true;
                                        }}
                                    >
                                        ${toShortUsername(msg.sender?.display_name ?? '', this._tp('composer.default_user_short'))}
                                    </button>
                                ` : ''}
                                ${hasEdited ? html`<span class="edited-badge">${this._tp('bubble.edited_short')}</span>` : ''}
                            </div>
                            ${hasHeaderEnd ? html`
                                <div class="bubble-header-end">
                                    ${this._isPinned() ? html`
                                        <span class="pin-mark" title=${this._tp('bubble.pinned_title')}>
                                            <platform-icon name="target" size="12"></platform-icon>
                                        </span>
                                    ` : ''}
                                    ${canFocusThread ? html`
                                        <button class="thread-btn" @click=${this._focusThread}>${this._tp('bubble.thread')}</button>
                                    ` : ''}
                                </div>
                            ` : ''}
                        </div>
                    ` : ''}
                    ${this._parentPreview()}
                    <div class="bubble-body">
                        <div class="bubble-contents">
                            <div class="contents-inner">
                                ${sorted.map(c => renderContent(c, this, (k, p) => this._tp(k, p)))}
                            </div>
                        </div>
                        ${this._renderTimeMeta()}
                    </div>
                    ${this._reactionsLine()}
                </div>
            </div>

            ${this._menuOpen ? html`
                <message-context-menu
                    .open=${true}
                    .anchorX=${this._menuX}
                    .anchorY=${this._menuY}
                    .isOwn=${isOwn}
                    .selectionMode=${this.selectionMode}
                    @menu-action=${this._onMenuAction}
                    @close=${() => { this._menuOpen = false; }}
                ></message-context-menu>
            ` : ''}

            ${this._profileOpen && this._profileUser
                ? html`
                <user-info-modal
                    .open=${true}
                    .profileUser=${this._profileUser}
                    @close=${this._onProfileClose}
                ></user-info-modal>
            `
                : ''}
        `;
    }
}

customElements.define('message-bubble', MessageBubble);
