/**
 * Блок ``conversation``: лента ходов (Task → ход) и композер. Читает store хоста и подписывается
 * на него; отправка, отмена, загрузка файлов и голос — методы хоста ``<platform-flow-ui>``.
 */

import { unsafeHTML } from '../../../assets/js/lit/directives/unsafe-html.min.js';
import { LitElement, html, nothing, type PropertyValues } from '../../lit-shim.js';
import { formatFileSize } from '../../utils/format-file-size.js';
import { blockStyles, renderBlocks } from '../blocks/registry.js';
import { activityChips } from '../blocks/platform.js';
import type { FlowUiBlock, FlowUiRecord, FlowUiRenderContext } from '../runtime/flow-ui-store.js';
import type { FlowUIStore } from '../runtime/flow-ui-store.js';
import type { ConversationTurn, ConversationTurnDialogueItem, FlowUiSettings } from '../runtime/conversation.js';
import { conversationTurns } from '../runtime/conversation.js';
import { resolveAgentIdentityImageSrc } from '../runtime/agent-identity-image.js';
import { resolvedText } from '../runtime/templating.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { markdownToHtml } from '../../utils/markdown.js';
import { flowUIText, hitlComposerSendLabel } from '../utils/text.js';
import { conversationStyles } from './flow-ui-conversation.styles.js';

const COMPOSER_MAX_PX = 200;

/** Поверхность ``<platform-flow-ui>``, нужная ленте и композеру. */
export interface FlowUiConversationHost {
    store: FlowUIStore;
    locale: string;
    interface: FlowUiRecord | null;
    platformUiOrigin: string;
    assistantTitle: unknown;
    contextId: string | null;
    editing: boolean;
    effectiveReadonly: boolean;
    capabilities: FlowUiRecord;
    hitlMode: string | null;
    userHandoff: { mode?: string } | null;
    voiceSessionActive: boolean;
    voiceSessionReady(): boolean;
    toggleVoiceSession(): void;
    cancelActiveTask(): void;
    sendText(text: string, files: File[] | FlowUiRecord[]): Promise<void>;
    blockContext(): FlowUiRenderContext;
    dispatchEvent(event: Event): boolean;
}

interface ActionButtonExtra {
    kind?: string;
    copied?: boolean;
}

export class FlowUIConversation extends LitElement {
    declare host: FlowUiConversationHost | null;
    declare settings: FlowUiSettings;
    declare blockId: string;
    declare editing: boolean;
    declare _text: string;
    declare _files: File[];
    declare _copiedTaskId: string;
    private _unsubscribe: (() => void) | null;
    private _stickToBottom: boolean;

    static override properties = {
        host: { attribute: false },
        settings: { attribute: false },
        blockId: { attribute: false },
        editing: { type: Boolean, reflect: true },
        _text: { state: true },
        _files: { state: true },
        _copiedTaskId: { state: true },
    };

    static override styles = [blockStyles, conversationStyles];

    constructor() {
        super();
        this.host = null;
        this.settings = {};
        this.blockId = '';
        this.editing = false;
        this._text = '';
        this._files = [];
        this._copiedTaskId = '';
        this._unsubscribe = null;
        this._stickToBottom = true;
    }

    override connectedCallback() {
        super.connectedCallback();
        this._subscribe();
    }

    override disconnectedCallback() {
        super.disconnectedCallback();
        if (this._unsubscribe) this._unsubscribe();
        this._unsubscribe = null;
    }

    override updated(changed: PropertyValues<this>) {
        if (changed.has('host')) this._subscribe();
        const feed = this.renderRoot.querySelector<HTMLElement>('.task-feed');
        if (feed && this._stickToBottom) feed.scrollTop = feed.scrollHeight;
    }

    private _subscribe() {
        if (this._unsubscribe) this._unsubscribe();
        this._unsubscribe = this.host ? this.host.store.subscribe(() => this.requestUpdate()) : null;
    }

    private _onFeedScroll(event: Event) {
        const feed = event.target as HTMLElement;
        this._stickToBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 48;
    }

    private get _locale(): string {
        return this.host?.locale ?? 'ru';
    }

    private _label(template: unknown): string {
        return this.host ? (resolvedText(template, this.host.store.state as FlowUiRecord) ?? '') : '';
    }

    private _identitySrc(): string {
        const host = this.host;
        if (!host) return '';
        return resolveAgentIdentityImageSrc({
            document: host.store.document,
            flowIdentity: (host.interface?.flow_identity as FlowUiRecord | null | undefined) ?? null,
            platformUiOrigin: host.platformUiOrigin,
        });
    }

    private _heroTitle(): string {
        const host = this.host;
        if (!host) return '';
        const override = typeof host.assistantTitle === 'string' ? host.assistantTitle.trim() : '';
        if (override !== '') return override;
        const look = host.interface?.look as FlowUiRecord | undefined;
        if (look && typeof look.assistant_title === 'string' && look.assistant_title.trim() !== '') return look.assistant_title.trim();
        const identity = host.interface?.flow_identity as FlowUiRecord | undefined;
        if (identity && typeof identity.title === 'string' && identity.title.trim() !== '') return identity.title.trim();
        return '';
    }

    private async _send() {
        const text = this._text.trim();
        const files = this._files;
        if (text === '' && files.length === 0) return;
        this._text = '';
        this._files = [];
        this._stickToBottom = true;
        if (this.host) await this.host.sendText(text, files);
    }

    private _onKeydown(event: KeyboardEvent) {
        if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
        event.preventDefault();
        void this._send();
    }

    private _growComposer(event: Event) {
        const target = event.target as HTMLTextAreaElement;
        this._text = target.value;
        target.style.height = 'auto';
        target.style.height = `${Math.min(target.scrollHeight, COMPOSER_MAX_PX)}px`;
    }

    private async _copy(turn: ConversationTurn) {
        await navigator.clipboard.writeText(turn.text);
        this._copiedTaskId = turn.taskId;
        setTimeout(() => { this._copiedTaskId = ''; }, 1500);
    }

    private _userFiles(files: FlowUiRecord[], extraClass: string) {
        if (files.length === 0) return nothing;
        return html`<div class="files ${extraClass}">${files.map((file) => html`<span class="composer-file-chip">
            ${flowUIGlyph('file-text', 12, this.host?.platformUiOrigin ?? '')}${String(file.original_name ?? '')}
        </span>`)}</div>`;
    }

    private _interrupt(turn: ConversationTurn) {
        const interrupt = turn.interrupt;
        if (!interrupt || interrupt.kind === 'user_message') return nothing;
        if (interrupt.kind === 'oauth_required') {
            return html`<div class="interrupt-card">
                ${interrupt.question !== '' ? html`<div>${interrupt.question}</div>` : ''}
                <a class="fu-button" data-variant="primary" href=${interrupt.authUrl} target="_blank" rel="noopener noreferrer">${flowUIText(this._locale, 'oauth_authorize')}</a>
            </div>`;
        }
        return interrupt.question !== '' ? html`<div class="interrupt-card">${interrupt.question}</div>` : nothing;
    }

    private _actionButton(className: string, label: string, glyph: string, onClick: () => void, extra: ActionButtonExtra = {}) {
        const origin = this.host?.platformUiOrigin ?? '';
        return html`<button type="button" class="msg-action ${className}" title=${label} aria-label=${label}
            data-kind=${extra.kind ?? nothing} ?data-copied=${extra.copied === true} @click=${onClick}>
            ${flowUIGlyph(glyph, 18, origin)}
        </button>`;
    }

    private _observabilityButtons(turn: ConversationTurn) {
        if (this.settings.show_trace_actions !== true) return nothing;
        const open = (kind: string) => this.host?.dispatchEvent(new CustomEvent('flow-ui-open-observability', {
            bubbles: true, composed: true, detail: { kind, taskId: turn.taskId, contextId: this.host?.contextId ?? null },
        }));
        return html`${this._actionButton('tracing-btn', flowUIText(this._locale, 'open_tracing'), 'git-branch', () => open('tracing'), { kind: 'tracing' })}
            ${this._actionButton('tracing-btn', flowUIText(this._locale, 'open_logs'), 'list', () => open('logs'), { kind: 'logs' })}`;
    }

    private _assistant(turn: ConversationTurn) {
        const streaming = !turn.settled && turn.interrupt === null;
        if (turn.text === '' && !streaming) return nothing;
        if (turn.text === '') return html`<div class="typing" aria-label=${flowUIText(this._locale, 'assistant_typing')}><i></i><i></i><i></i></div>`;
        const author = turn.author && typeof turn.author.name === 'string' ? turn.author.name : '';
        return html`<div class="bubble assistant" data-task-id=${turn.taskId}>
            ${author !== '' ? html`<div class="author">${author}</div>` : ''}
            <div class="assistant-response fu-prose ${streaming ? 'streaming' : ''}">${unsafeHTML(markdownToHtml(turn.text))}</div>
            ${turn.settled ? html`<div class="bubble-observability-actions">
                ${this._actionButton(
                    'copy-btn',
                    flowUIText(this._locale, this._copiedTaskId === turn.taskId ? 'message_copied' : 'message_copy'),
                    this._copiedTaskId === turn.taskId ? 'check' : 'copy',
                    () => this._copy(turn),
                    { copied: this._copiedTaskId === turn.taskId },
                )}
                ${this._observabilityButtons(turn)}
            </div>` : ''}
        </div>`;
    }

    private _dialogue(turn: ConversationTurn) {
        return turn.dialogue.map((item: ConversationTurnDialogueItem) => item.role === 'user'
            ? html`<div class="bubble user">${item.text}</div>`
            : html`<div class="bubble operator"><div class="author">${item.author && typeof item.author.name === 'string' ? item.author.name : flowUIText(this._locale, 'operator_label')}</div>${unsafeHTML(markdownToHtml(item.text))}</div>`);
    }

    private _turn(turn: ConversationTurn) {
        const host = this.host;
        const cards = turn.cards.length > 0 && host ? html`<div class="cards">${renderBlocks(turn.cards as FlowUiBlock[], host.blockContext())}</div>` : nothing;
        return html`<article class="task" data-task-id=${turn.taskId} data-state=${turn.state}>
            ${turn.user ? html`${turn.user.text !== '' ? html`<div class="bubble user">${turn.user.text}</div>` : ''}${this._userFiles(turn.user.files, 'user')}` : ''}
            ${turn.activity.length > 0 ? activityChips(turn.activity) : ''}
            ${cards}
            ${turn.reasoning !== '' ? html`<details class="reasoning"><summary>${flowUIText(this._locale, 'reasoning')}</summary><pre>${turn.reasoning}</pre></details>` : ''}
            ${this._assistant(turn)}
            ${this._dialogue(turn)}
            ${this._interrupt(turn)}
            ${turn.error !== '' ? html`<div class="bubble error" role="alert">${turn.error}</div>` : ''}
            ${turn.state === 'TASK_STATE_CANCELED' ? html`<div class="author">${flowUIText(this._locale, 'task_canceled')}</div>` : ''}
        </article>`;
    }

    private _pending() {
        const pending = this.host?.store.pending as FlowUiRecord | null;
        if (!pending) return nothing;
        return html`<article class="task" data-pending="true">
            ${pending.text !== '' ? html`<div class="bubble user">${pending.text}</div>` : ''}
            ${this._userFiles(Array.isArray(pending.files) ? pending.files as FlowUiRecord[] : [], 'user')}
            <div class="typing"><i></i><i></i><i></i></div>
        </article>`;
    }

    private _greeting() {
        const greeting = this._label(this.settings.greeting ?? '');
        const prompts = (Array.isArray(this.settings.suggested_prompts) ? this.settings.suggested_prompts : [])
            .map((item) => this._label(item))
            .filter((item) => item !== '');
        const title = this._heroTitle();
        return html`<div class="greeting">
            <img class="greeting-mark" src=${this._identitySrc()} alt="">
            ${title !== '' ? html`<h2 class="greeting-title">${title}</h2>` : ''}
            ${greeting !== '' ? html`<p>${greeting}</p>` : ''}
            ${prompts.length > 0 ? html`<div class="fu-prompts">${prompts.map((prompt) => html`<button type="button" ?disabled=${this.host?.effectiveReadonly ?? true}
                @click=${() => { this._text = prompt; void this._send(); }}>${prompt}</button>`)}</div>` : ''}
        </div>`;
    }

    /** В редакторе композер показывается целиком, но инертен: WYSIWYG без отправки. */
    private _composer() {
        const host = this.host;
        if (!host) return nothing;
        const editing = host.editing === true;
        const waitingOperator = !editing && host.userHandoff?.mode === 'single_reply';
        if (host.effectiveReadonly && !editing && !waitingOperator) return nothing;
        const locale = this._locale;
        const turnActive = !editing && host.store.turnActive;
        const streaming = !editing && host.store.streaming;
        const canStop = !editing && host.store.taskRunning && this.settings.allow_cancel !== false && host.capabilities.cancel === true && host.hitlMode === null;
        const sendLabel = hitlComposerSendLabel(locale, host.hitlMode) ?? flowUIText(locale, 'composer_send');
        const placeholder = this._label(this.settings.placeholder ?? '') || flowUIText(locale, 'composer_placeholder');
        const filesAllowed = editing || (!waitingOperator && host.capabilities.files === true);
        const voiceAllowed = this.settings.allow_voice !== false && !waitingOperator
            && (editing || (host.capabilities.voice === true && host.hitlMode === null && host.voiceSessionReady()));
        const canSend = !editing && !waitingOperator && (this._text.trim() !== '' || this._files.length > 0) && !turnActive && !streaming;
        const voiceLabel = flowUIText(locale, host.voiceSessionActive ? 'voice_stop' : 'voice_start');
        return html`<div class="composer" data-editing=${editing ? 'true' : nothing}>
            ${this._files.length > 0 ? html`<div class="files">${this._files.map((file: File, index: number) => html`<span class="composer-file-chip">
                ${file.name} · ${formatFileSize(file.size)}
                <button type="button" aria-label=${flowUIText(locale, 'remove_file', { name: file.name })}
                    @click=${() => { this._files = this._files.filter((_: File, i: number) => i !== index); }}>${flowUIGlyph('close', 12, host.platformUiOrigin)}</button>
            </span>`)}</div>` : ''}
            <textarea data-canon="composer" rows="1" .value=${this._text} placeholder=${placeholder} ?readonly=${waitingOperator}
                aria-label=${flowUIText(locale, 'conversation_feed')}
                @input=${(event: Event) => this._growComposer(event)}
                @keydown=${(event: KeyboardEvent) => this._onKeydown(event)}></textarea>
            <div class="actions">
                ${filesAllowed ? html`<label class="icon-btn" title=${flowUIText(locale, 'attach_files')}>
                    ${flowUIGlyph('paperclip', 16, host.platformUiOrigin)}
                    <input type="file" multiple hidden @change=${(event: Event) => {
                        const input = event.target as HTMLInputElement;
                        this._files = [...this._files, ...Array.from(input.files ?? [])];
                        input.value = '';
                    }}>
                </label>` : ''}
                ${voiceAllowed ? html`<button type="button" class="icon-btn composer-voice-session" aria-pressed=${host.voiceSessionActive ? 'true' : 'false'}
                    aria-label=${voiceLabel} title=${voiceLabel}
                    @click=${() => host.toggleVoiceSession()}>${flowUIGlyph(host.voiceSessionActive ? 'mic-off' : 'mic', 16, host.platformUiOrigin)}</button>` : ''}
                <span class="spacer"></span>
                ${canStop
                    ? html`<button type="button" class="icon-btn stop" aria-label=${flowUIText(locale, 'composer_stop')} title=${flowUIText(locale, 'composer_stop')}
                        @click=${() => host.cancelActiveTask()}>${flowUIGlyph('square', 12, host.platformUiOrigin)}</button>`
                    : html`<button type="button" class="icon-btn send" ?disabled=${!canSend} aria-label=${sendLabel} title=${sendLabel}
                        @click=${() => this._send()}>${flowUIGlyph('send', 16, host.platformUiOrigin)}</button>`}
            </div>
        </div>`;
    }

    override render() {
        if (!this.host) return nothing;
        const turns = conversationTurns(this.host.store, this.settings, this._locale);
        const empty = turns.length === 0 && this.host.store.pending === null;
        this.toggleAttribute('data-empty', empty);
        return html`<div class="task-feed" role="log" aria-label=${flowUIText(this._locale, 'conversation_feed')} @scroll=${(event: Event) => this._onFeedScroll(event)}>
            ${empty ? this._greeting() : turns.map((turn) => this._turn(turn))}
            ${this._pending()}
        </div>
        ${this._composer()}`;
    }
}

if (!customElements.get('flow-ui-conversation')) customElements.define('flow-ui-conversation', FlowUIConversation);
