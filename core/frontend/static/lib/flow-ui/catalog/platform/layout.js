import { html, nothing } from '../../../lit-shim.js';
import { flowUIComponentRenderer } from '../registry.js';
import { flowUIGlyph } from '../flow-ui-glyph.js';
import {
    componentFieldError,
    componentHasRequiredCheck,
    labelOfComponent,
    optionalComponentProperty,
    renderChildren,
    renderFieldError,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';
import {
    activeConversationTask,
    hasConversationContent,
    mergeConversationTasks,
} from './conversation-turn.js';
import { flowUIText } from '../../utils/text.js';
import { openFlowUISessionFile } from '../../utils/open-session-file.js';
import { renderVoiceInput } from './voice.js';

function isComposerForm(component) {
    if (optionalComponentProperty(component, 'presentation') === 'composer') return true;
    if (optionalComponentProperty(component, 'formId') === 'message-form') return true;
    return component.component_id === 'message-form';
}

/**
 * Conversation shell detection: explicit presentation, or structural chat template
 * (ConversationFeed / conversation ArtifactFeed). Editor may strip presentation when
 * promoting PageShell to grid — runtime must still recognize the chat contract.
 */
function isConversationPageShell(host, component) {
    if (optionalComponentProperty(component, 'presentation') === 'conversation') {
        return true;
    }
    const components = host.surface?.components;
    if (!components || typeof components !== 'object') return false;
    for (const childId of component.children || []) {
        const child = components[childId];
        if (!child || typeof child !== 'object') continue;
        if (child.type === 'ConversationFeed') return true;
        if (child.type === 'ArtifactFeed'
            && optionalComponentProperty(child, 'presentation') === 'conversation') {
            return true;
        }
    }
    return false;
}

function isChatHeaderSection(host, component) {
    if (optionalComponentProperty(component, 'presentation') === 'chat-header') {
        return true;
    }
    const components = host.surface?.components;
    if (!components || typeof components !== 'object') return false;
    return (component.children || []).some((childId) => {
        const child = components[childId];
        return child && typeof child === 'object' && child.type === 'AgentIdentity';
    });
}

/** Conversation shell always uses flex geometry (editor + runtime). */
const CONVERSATION_FLEX_LAYOUT = Object.freeze({
    mode: 'flex',
    flex: Object.freeze({
        direction: 'column',
        gap_token: 'space.0',
        wrap: false,
        align_items: 'stretch',
        justify_content: 'start',
    }),
});

/** Composer attach / file chips — capabilities.files only (not the tray policy). */
function filesCapabilityAllowed(host) {
    const capabilities = host.controller?.profile?.capabilities;
    if (capabilities && capabilities.files === false) return false;
    return true;
}

function fileRefLabel(ref) {
    if (!ref || typeof ref !== 'object') {
        throw new Error('flow-ui: file chip requires a FileRef object');
    }
    if (typeof ref.original_name === 'string' && ref.original_name.trim() !== '') {
        return ref.original_name;
    }
    if (typeof ref.filename === 'string' && ref.filename.trim() !== '') {
        return ref.filename;
    }
    if (typeof ref.file_id === 'string' && ref.file_id.trim() !== '') {
        return ref.file_id;
    }
    throw new Error('flow-ui: FileRef missing original_name/filename/file_id');
}

function renderComposerFileChips(host, fileUpload) {
    if (!fileUpload) return nothing;
    const value = resolveBound(host.surface, fileUpload, 'value', host.tasks);
    const refs = Array.isArray(value) ? value : [];
    if (!refs.length) return nothing;
    return html`<div class="composer-files" role="list">
        ${refs.map((ref) => html`<span class="composer-file-chip" role="listitem">
            <button
                type="button"
                class="composer-file-open"
                aria-label=${flowUIText(host.locale, 'open_file', { name: fileRefLabel(ref) })}
                title=${fileRefLabel(ref)}
                @click=${() => openFlowUISessionFile(ref, 'flow_ui_composer')}
            >
                ${flowUIGlyph('file', 14, host.platformUiOrigin)}
                <span class="composer-file-name">${fileRefLabel(ref)}</span>
            </button>
            ${host.readonly ? nothing : html`<button
                type="button"
                class="composer-file-remove"
                aria-label=${flowUIText(host.locale, 'remove_file', { name: fileRefLabel(ref) })}
                @click=${() => host._removeUploadedFile(fileUpload, ref.file_id)}
            >${flowUIGlyph('x', 12, host.platformUiOrigin)}</button>`}
        </span>`)}
    </div>`;
}

function renderComposerAttach(host, component) {
    const label = labelOfComponent(host, component) || flowUIText(host.locale, 'attach_files');
    const upload = host.uploadState?.[component.component_id] || {};
    const multiple = optionalComponentProperty(component, 'multiple') !== false;
    const inputId = `flow-ui-file-${component.component_id}`;
    const busy = upload.busy === true;
    const disabled = host.readonly || busy;
    return html`<div class="composer-attach">
        <input
            id=${inputId}
            class="file-upload-input"
            type="file"
            ?multiple=${multiple}
            ?disabled=${disabled}
            @change=${(event) => host._upload(component, event)}
        >
        <button
            type="button"
            class="circle-btn composer-attach-btn"
            ?disabled=${disabled}
            aria-label=${label}
            title=${label}
            aria-busy=${busy ? 'true' : 'false'}
            @click=${() => {
                const input = host.renderRoot?.getElementById(inputId);
                if (!input) {
                    throw new Error(`flow-ui: file input ${inputId} missing`);
                }
                input.click();
            }}
        >${busy
            ? html`<span class="composer-attach-spinner" aria-hidden="true"></span>`
            : flowUIGlyph('paperclip', 18, host.platformUiOrigin)}</button>
        ${upload.error ? html`<span class="upload-error">${upload.error}</span>` : nothing}
    </div>`;
}

function autosizeComposerTextarea(textarea) {
    if (!(textarea instanceof HTMLTextAreaElement)) return;
    textarea.style.height = 'auto';
    const next = Math.min(Math.max(textarea.scrollHeight, 24), 160);
    textarea.style.height = `${next}px`;
}

export function renderPageShell(host, component) {
    const conversation = isConversationPageShell(host, component);
    let shellClass = 'page-shell';
    if (conversation) {
        const feedTasks = mergeConversationTasks(host.tasks, host.controller?.activeContext?.pendingTurns);
        shellClass = hasConversationContent(feedTasks)
            ? 'page-shell page-shell--conversation'
            : 'page-shell page-shell--conversation page-shell--conversation-empty';
    }
    // Conversation shell is always flex geometry (editor + runtime). Author grid on
    // PageShell with ConversationFeed produced empty rows and clipped the feed when
    // message-form sat at a high row_start after migrate/insert.
    const layoutComponent = conversation
        ? { ...component, container_layout: CONVERSATION_FLEX_LAYOUT }
        : component;
    return wrapFlowNode(
        host,
        layoutComponent,
        html`${renderChildren(host, component)}`,
        { extraClass: shellClass },
    );
}

export function renderNavigation(host, component) {
    return wrapFlowNode(host, component, html`${renderChildren(host, component)}`);
}

export function renderSection(host, component) {
    const sectionClass = isChatHeaderSection(host, component)
        ? 'section section--chat-header'
        : 'section';
    return wrapFlowNode(host, component, renderChildren(host, component), {
        surfaceTag: 'section',
        surfaceClass: sectionClass,
    });
}

export function renderGrid(host, component) {
    return wrapFlowNode(host, component, html`${renderChildren(host, component)}`);
}

export function renderStack(host, component) {
    return wrapFlowNode(host, component, html`${renderChildren(host, component)}`);
}

export function renderForm(host, component) {
    if (isComposerForm(component)) {
        const children = (component.children || [])
            .map((id) => host.surface.components[id])
            .filter(Boolean);
        const fileUpload = children.find((child) => child.type === 'FileUpload');
        const textArea = children.find((child) => child.type === 'TextArea');
        const voiceInput = children.find((child) => child.type === 'VoiceInput');
        const submit = children.find((child) => child.type === 'Button');
        const submitRenderer = submit ? flowUIComponentRenderer(submit.type) : null;
        const messageValue = textArea
            ? resolveBound(host.surface, textArea, 'value', host.tasks)
            : '';
        const placeholder = textArea
            ? (optionalComponentProperty(textArea, 'placeholder')
                || flowUIText(host.locale, 'composer_placeholder'))
            : flowUIText(host.locale, 'composer_placeholder');
        const showFiles = Boolean(fileUpload) && filesCapabilityAllowed(host);
        const fileRefs = showFiles
            ? resolveBound(host.surface, fileUpload, 'value', host.tasks)
            : [];
        const hasFiles = Array.isArray(fileRefs) && fileRefs.length > 0;
        const canSend = !host.readonly
            && (String(messageValue ?? '').trim() !== '' || hasFiles);
        const textRequired = textArea ? componentHasRequiredCheck(textArea) : false;
        const textInvalid = textArea ? componentFieldError(host, textArea) !== '' : false;
        // Composer submit control state machine: send → busy (submit in flight,
        // no task projection yet) → stop (in-flight task, cancel allowed) → send.
        // INPUT_REQUIRED / AUTH_REQUIRED are settled: composer returns to send.
        const submitting = host.controller?.activeContext?.submitting === true;
        const hitlOperator = host.hitlMode === 'takeover' || host.hitlMode === 'single_reply';
        const activeTask = hitlOperator ? null : activeConversationTask(host.tasks);
        const cancelAllowed = host.controller?.profile?.capabilities?.cancel === true;
        const composerState = activeTask !== null
            ? (cancelAllowed ? 'stop' : 'busy')
            : (submitting ? 'busy' : 'send');
        return wrapFlowNode(
            host,
            component,
            html`<div
                class="field-group field-group--composer"
                role="form"
                aria-label=${flowUIText(host.locale, 'message_composer')}
            >
                <div class="composer-shell">
                    ${showFiles ? renderComposerFileChips(host, fileUpload) : nothing}
                    <div class="composer-row">
                        <div class="composer-toolbar-start">
                            ${showFiles ? renderComposerAttach(host, fileUpload) : nothing}
                        </div>
                        <div class="composer-body">
                            ${textArea ? html`<textarea
                                data-canon="composer"
                                .value=${String(messageValue ?? '')}
                                rows="1"
                                placeholder=${String(placeholder)}
                                ?readonly=${host.readonly}
                                ?required=${textRequired}
                                aria-required=${textRequired ? 'true' : 'false'}
                                aria-invalid=${textInvalid ? 'true' : 'false'}
                                @input=${(event) => {
                                    host._change(textArea, 'value', event.target.value);
                                    autosizeComposerTextarea(event.target);
                                }}
                                @keydown=${(event) => {
                                    if (event.isComposing) return;
                                    if (event.key === 'Enter' && !event.shiftKey) {
                                        event.preventDefault();
                                        if (submit && canSend && composerState === 'send') {
                                            host._action(submit, 'press');
                                        }
                                    }
                                }}
                            ></textarea>` : nothing}
                        </div>
                        <div class="composer-toolbar-end">
                            ${voiceInput
                                ? renderVoiceInput(host, {
                                    ...voiceInput,
                                    properties: {
                                        ...(voiceInput.properties || {}),
                                        presentation: 'composer',
                                    },
                                }, { dense: true })
                                : nothing}
                            ${submit && submitRenderer ? (() => {
                                if (submit.placement == null || typeof submit.placement !== 'object') {
                                    throw new Error(
                                        `flow-ui Form: submit ${submit.component_id} requires placement`,
                                    );
                                }
                                return submitRenderer(host, {
                                    component_id: submit.component_id,
                                    type: submit.type,
                                    kind: submit.kind,
                                    children: submit.children,
                                    bindings: submit.bindings,
                                    actions: submit.actions,
                                    container_layout: null,
                                    placement: submit.placement,
                                    checks: submit.checks || [],
                                    properties: {
                                        ...(submit.properties || {}),
                                        presentation: 'composer',
                                        composerState,
                                        disabled: composerState === 'send' && !canSend,
                                    },
                                });
                            })() : nothing}
                        </div>
                    </div>
                    ${textArea ? renderFieldError(host, textArea) : nothing}
                    ${showFiles && fileUpload ? renderFieldError(host, fileUpload) : nothing}
                </div>
            </div>`,
            { applyContainerLayout: false },
        );
    }
    return wrapFlowNode(host, component, renderChildren(host, component), {
        surfaceClass: 'field-group',
        surfaceRole: 'form',
    });
}

export function renderFieldGroup(host, component) {
    return wrapFlowNode(host, component, renderChildren(host, component), {
        surfaceClass: 'field-group',
    });
}

export function renderConversationFeed(host, component) {
    const jump = host.feedJump === true
        ? html`<div class="scroll-to-bottom-rail">
            <button
                type="button"
                class="scroll-to-bottom"
                aria-label=${flowUIText(host.locale, 'scroll_to_bottom')}
                title=${flowUIText(host.locale, 'scroll_to_bottom')}
                @click=${() => host._scrollFeedToBottom()}
            >${flowUIGlyph('arrow-down', 16, host.platformUiOrigin)}</button>
        </div>`
        : nothing;
    return wrapFlowNode(host, component, html`${renderChildren(host, component)}${jump}`);
}

export function renderPageLink(host, component) {
    const pageId = optionalComponentProperty(component, 'pageId')
        ?? optionalComponentProperty(component, 'targetPageId')
        ?? optionalComponentProperty(component, 'page_id');
    const label = labelOfComponent(host, component) || flowUIText(host.locale, 'open');
    return wrapFlowNode(
        host,
        component,
        html`<button
            class="secondary"
            ?disabled=${pageId == null || pageId === ''}
            @click=${() => {
                if (pageId == null || pageId === '') {
                    throw new Error(`flow-ui: PageLink ${component.component_id} missing pageId`);
                }
                host.controller?.navigate(pageId);
            }}
        >${label}</button>`,
    );
}

export function registerPlatformLayout(register) {
    register('PageShell', renderPageShell);
    register('Navigation', renderNavigation);
    register('PageLink', renderPageLink);
    register('Section', renderSection);
    register('Grid', renderGrid);
    register('Stack', renderStack);
    register('Form', renderForm);
    register('FieldGroup', renderFieldGroup);
    register('ConversationFeed', renderConversationFeed);
}
