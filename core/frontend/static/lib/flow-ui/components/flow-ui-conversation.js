/**
 * Блок ``conversation``: лента ходов (Task → ход) и композер. Читает store хоста и подписывается
 * на него; отправка, отмена, загрузка файлов и голос — методы хоста ``<platform-flow-ui>``.
 */

import { unsafeHTML } from '../../../assets/js/lit/directives/unsafe-html.min.js';
import { LitElement, html, nothing } from '../../lit-shim.js';
import { formatFileSize } from '../../utils/format-file-size.js';
import { blockStyles, renderBlocks } from '../blocks/registry.js';
import { activityChips } from '../blocks/platform.js';
import { conversationTurns } from '../runtime/conversation.js';
import { resolveAgentIdentityImageSrc } from '../runtime/agent-identity-image.js';
import { resolvedText } from '../runtime/templating.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { markdownToHtml } from '../../utils/markdown.js';
import { flowUIText, hitlComposerSendLabel } from '../utils/text.js';
import { conversationStyles } from './flow-ui-conversation.styles.js';

const COMPOSER_MAX_PX = 200;

export class FlowUIConversation extends LitElement {
    static properties = {
        host: { attribute: false },
        settings: { attribute: false },
        blockId: { attribute: false },
        _text: { state: true },
        _files: { state: true },
        _copiedTaskId: { state: true },
    };

    static styles = [blockStyles, conversationStyles];

    constructor() {
        super();
        this.host = null;
        this.settings = {};
        this.blockId = '';
        this._text = '';
        this._files = [];
        this._copiedTaskId = '';
        this._unsubscribe = null;
        this._stickToBottom = true;
    }

    connectedCallback() {
        super.connectedCallback();
        this._subscribe();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._unsubscribe) this._unsubscribe();
        this._unsubscribe = null;
    }

    updated(changed) {
        if (changed.has('host')) this._subscribe();
        const feed = this.renderRoot.querySelector('.task-feed');
        if (feed && this._stickToBottom) feed.scrollTop = feed.scrollHeight;
    }

    _subscribe() {
        if (this._unsubscribe) this._unsubscribe();
        this._unsubscribe = this.host ? this.host.store.subscribe(() => this.requestUpdate()) : null;
    }

    _onFeedScroll(event) {
        const feed = event.target;
        this._stickToBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 48;
    }

    get _locale() {
        return this.host.locale;
    }

    _label(template) {
        return resolvedText(template, this.host.store.state) ?? '';
    }

    _identitySrc() {
        return resolveAgentIdentityImageSrc({
            document: this.host.store.document,
            flowIdentity: this.host.interface?.flow_identity ?? null,
            platformUiOrigin: this.host.platformUiOrigin,
        });
    }

    _heroTitle() {
        const override = typeof this.host.assistantTitle === 'string' ? this.host.assistantTitle.trim() : '';
        if (override !== '') return override;
        const look = this.host.interface?.look;
        if (look && typeof look.assistant_title === 'string' && look.assistant_title.trim() !== '') return look.assistant_title.trim();
        const identity = this.host.interface?.flow_identity;
        if (identity && typeof identity.title === 'string' && identity.title.trim() !== '') return identity.title.trim();
        return '';
    }

    async _send() {
        const text = this._text.trim();
        const files = this._files;
        if (text === '' && files.length === 0) return;
        this._text = '';
        this._files = [];
        this._stickToBottom = true;
        await this.host.sendText(text, files);
    }

    _onKeydown(event) {
        if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
        event.preventDefault();
        void this._send();
    }

    _growComposer(event) {
        this._text = event.target.value;
        event.target.style.height = 'auto';
        event.target.style.height = `${Math.min(event.target.scrollHeight, COMPOSER_MAX_PX)}px`;
    }

    async _copy(turn) {
        await navigator.clipboard.writeText(turn.text);
        this._copiedTaskId = turn.taskId;
        setTimeout(() => { this._copiedTaskId = ''; }, 1500);
    }

    _userFiles(files, extraClass) {
        if (files.length === 0) return nothing;
        return html`<div class="files ${extraClass}">${files.map((file) => html`<span class="composer-file-chip">
            ${flowUIGlyph('file-text', 12, this.host.platformUiOrigin)}${file.original_name}
        </span>`)}</div>`;
    }

    _interrupt(turn) {
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

    _observabilityButtons(turn) {
        if (this.settings.show_trace_actions !== true) return nothing;
        const open = (kind) => this.host.dispatchEvent(new CustomEvent('flow-ui-open-observability', {
            bubbles: true, composed: true, detail: { kind, taskId: turn.taskId, contextId: this.host.contextId },
        }));
        return html`<button type="button" class="tracing-btn" @click=${() => open('tracing')}>${flowUIText(this._locale, 'open_tracing')}</button>
            <button type="button" class="tracing-btn" @click=${() => open('logs')}>${flowUIText(this._locale, 'open_logs')}</button>`;
    }

    _assistant(turn) {
        const streaming = !turn.settled && turn.interrupt === null;
        if (turn.text === '' && !streaming) return nothing;
        if (turn.text === '') return html`<div class="typing" aria-label=${flowUIText(this._locale, 'assistant_typing')}><i></i><i></i><i></i></div>`;
        const author = turn.author && typeof turn.author.name === 'string' ? turn.author.name : '';
        return html`<div class="bubble assistant" data-task-id=${turn.taskId}>
            ${author !== '' ? html`<div class="author">${author}</div>` : ''}
            <div class="assistant-response fu-prose ${streaming ? 'streaming' : ''}">${unsafeHTML(markdownToHtml(turn.text))}</div>
            ${turn.settled ? html`<div class="bubble-observability-actions">
                <button type="button" class="copy-btn" @click=${() => this._copy(turn)}>${flowUIText(this._locale, this._copiedTaskId === turn.taskId ? 'message_copied' : 'message_copy')}</button>
                ${this._observabilityButtons(turn)}
            </div>` : ''}
        </div>`;
    }

    _dialogue(turn) {
        return turn.dialogue.map((item) => item.role === 'user'
            ? html`<div class="bubble user">${item.text}</div>`
            : html`<div class="bubble operator"><div class="author">${item.author && typeof item.author.name === 'string' ? item.author.name : flowUIText(this._locale, 'operator_label')}</div>${unsafeHTML(markdownToHtml(item.text))}</div>`);
    }

    _turn(turn) {
        const cards = turn.cards.length > 0 ? html`<div class="cards">${renderBlocks(turn.cards, this.host.blockContext())}</div>` : nothing;
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

    _pending() {
        const pending = this.host.store.pending;
        if (!pending) return nothing;
        return html`<article class="task" data-pending="true">
            ${pending.text !== '' ? html`<div class="bubble user">${pending.text}</div>` : ''}
            ${this._userFiles(pending.files, 'user')}
            <div class="typing"><i></i><i></i><i></i></div>
        </article>`;
    }

    _greeting() {
        const greeting = this._label(this.settings.greeting ?? '');
        const prompts = (this.settings.suggested_prompts ?? []).map((item) => this._label(item)).filter((item) => item !== '');
        const title = this._heroTitle();
        return html`<div class="greeting">
            <img class="greeting-mark" src=${this._identitySrc()} alt="">
            ${title !== '' ? html`<h2 class="greeting-title">${title}</h2>` : ''}
            ${greeting !== '' ? html`<p>${greeting}</p>` : ''}
            ${prompts.length > 0 ? html`<div class="fu-prompts">${prompts.map((prompt) => html`<button type="button" ?disabled=${this.host.effectiveReadonly}
                @click=${() => { this._text = prompt; void this._send(); }}>${prompt}</button>`)}</div>` : ''}
        </div>`;
    }

    /** В редакторе композер показывается целиком, но инертен: WYSIWYG без отправки. */
    _composer() {
        const host = this.host;
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
            ${this._files.length > 0 ? html`<div class="files">${this._files.map((file, index) => html`<span class="composer-file-chip">
                ${file.name} · ${formatFileSize(file.size)}
                <button type="button" aria-label=${flowUIText(locale, 'remove_file', { name: file.name })}
                    @click=${() => { this._files = this._files.filter((_, i) => i !== index); }}>${flowUIGlyph('close', 12, host.platformUiOrigin)}</button>
            </span>`)}</div>` : ''}
            <textarea data-canon="composer" rows="1" .value=${this._text} placeholder=${placeholder} ?readonly=${waitingOperator}
                aria-label=${flowUIText(locale, 'conversation_feed')}
                @input=${(event) => this._growComposer(event)}
                @keydown=${(event) => this._onKeydown(event)}></textarea>
            <div class="actions">
                ${filesAllowed ? html`<label class="icon-btn" title=${flowUIText(locale, 'attach_files')}>
                    ${flowUIGlyph('paperclip', 16, host.platformUiOrigin)}
                    <input type="file" multiple hidden @change=${(event) => { this._files = [...this._files, ...event.target.files]; event.target.value = ''; }}>
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

    render() {
        if (!this.host) return nothing;
        const turns = conversationTurns(this.host.store, this.settings, this._locale);
        const empty = turns.length === 0 && this.host.store.pending === null;
        this.toggleAttribute('data-empty', empty);
        return html`<div class="task-feed" role="log" aria-label=${flowUIText(this._locale, 'conversation_feed')} @scroll=${(event) => this._onFeedScroll(event)}>
            ${empty ? this._greeting() : turns.map((turn) => this._turn(turn))}
            ${this._pending()}
        </div>
        ${this._composer()}`;
    }
}

if (!customElements.get('flow-ui-conversation')) customElements.define('flow-ui-conversation', FlowUIConversation);
