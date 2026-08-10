/**
 * Catalog VoiceInput — authorable mic / duplex control (constructor + runtime).
 * Composer discovers this child; Form must not inject voice chrome.
 */

import { html } from '../../../lit-shim.js';
import { hasFactory } from '../../../events/factory-registry.js';
import { hasPlatformBus } from '../../../events/bus-singleton.js';
import '../../../components/platform-voice-dictation.js';
import { flowUIGlyph } from '../flow-ui-glyph.js';
import {
    optionalComponentProperty,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';
import { flowUIText } from '../../utils/text.js';

export function voiceCapabilityAllowed(host) {
    if (!hasPlatformBus() || !hasFactory('platform/voice_dictation')) {
        return false;
    }
    const policy = host.controller?.document?.policy;
    if (policy && policy.allow_voice === false) {
        return false;
    }
    const capabilities = host.controller?.profile?.capabilities;
    if (capabilities && capabilities.voice === false) {
        return false;
    }
    return true;
}

function resolveVoiceMode(component) {
    const mode = optionalComponentProperty(component, 'mode');
    if (mode === 'session' || mode === 'dictation') {
        return mode;
    }
    return 'dictation';
}

function resolveTargetTextArea(host, component) {
    const binding = component.bindings?.value;
    if (typeof binding === 'string' && binding.trim() !== '') {
        return component;
    }
    const parent = findParentForm(host, component.component_id);
    if (!parent) {
        return null;
    }
    for (const childId of parent.children || []) {
        const child = host.surface?.components?.[childId];
        if (child && child.type === 'TextArea') {
            return child;
        }
    }
    return null;
}

function findParentForm(host, componentId) {
    const components = host.surface?.components;
    if (!components || typeof components !== 'object') {
        return null;
    }
    for (const candidate of Object.values(components)) {
        if (!candidate || typeof candidate !== 'object') continue;
        if ((candidate.children || []).includes(componentId) && candidate.type === 'Form') {
            return candidate;
        }
    }
    return null;
}

function appendSpokenText(host, textArea, spoken) {
    if (typeof spoken !== 'string' || spoken.trim() === '') {
        throw new Error('flow-ui: voice dictation returned empty text');
    }
    const current = String(resolveBound(host.surface, textArea, 'value', host.tasks) ?? '');
    const next = current.trim() === ''
        ? spoken.trim()
        : `${current.trimEnd()} ${spoken.trim()}`;
    host._change(textArea, 'value', next);
}

function sessionInfrastructureReady(host) {
    if (typeof host.voiceSessionReady !== 'function') {
        return false;
    }
    return host.voiceSessionReady() === true;
}

function renderDictationControl(host, component, textArea, dense) {
    if (!textArea) {
        return wrapFlowNode(
            host,
            component,
            html`<span class="voice-input-missing" role="status">${flowUIText(host.locale, 'voice_bind_missing')}</span>`,
        );
    }
    const interactive = voiceCapabilityAllowed(host) && !host.readonly;
    return wrapFlowNode(
        host,
        component,
        html`<platform-voice-dictation
            density=${dense ? 'dense' : 'default'}
            ?disabled=${!interactive}
            @transcribed=${(event) => {
                appendSpokenText(host, textArea, event.detail?.text);
            }}
        ></platform-voice-dictation>`,
    );
}

function renderSessionControl(host, component, dense) {
    const interactive = voiceCapabilityAllowed(host)
        && sessionInfrastructureReady(host)
        && !host.readonly;
    if (!interactive) {
        // voice.mdc: without duplex infra, catalog voice falls back to dictation.
        const textArea = resolveTargetTextArea(host, component);
        return renderDictationControl(host, component, textArea, dense);
    }
    const active = host.voiceSessionActive === true;
    const label = flowUIText(
        host.locale,
        active ? 'voice_session_stop_aria' : 'voice_session_start_aria',
    );
    return wrapFlowNode(
        host,
        component,
        html`<button
            type="button"
            class=${dense ? 'circle-btn composer-voice-session' : 'voice-session-btn'}
            aria-pressed=${active ? 'true' : 'false'}
            aria-label=${label}
            title=${label}
            @click=${() => {
                if (typeof host.toggleVoiceSession !== 'function') {
                    throw new Error('flow-ui: VoiceInput session requires host.toggleVoiceSession');
                }
                host.toggleVoiceSession();
            }}
        >${flowUIGlyph(active ? 'mic-off' : 'mic', dense ? 18 : 20)}</button>`,
    );
}

/**
 * @param {object} host
 * @param {object} component
 * @param {{ dense?: boolean }} [options]
 */
export function renderVoiceInput(host, component, options = {}) {
    const dense = options.dense === true
        || optionalComponentProperty(component, 'presentation') === 'composer';
    if (!voiceCapabilityAllowed(host)) {
        // Component stays in the document; capability gate disables interaction.
        return wrapFlowNode(
            host,
            component,
            html`<button
                type="button"
                class=${dense ? 'circle-btn composer-voice-session' : 'voice-session-btn'}
                disabled
                aria-disabled="true"
                title=${flowUIText(host.locale, 'voice_unavailable')}
                aria-label=${flowUIText(host.locale, 'voice_unavailable')}
            >${flowUIGlyph('mic', dense ? 18 : 20)}</button>`,
        );
    }
    const mode = resolveVoiceMode(component);
    if (mode === 'session') {
        return renderSessionControl(host, component, dense);
    }
    const textArea = resolveTargetTextArea(host, component);
    return renderDictationControl(host, component, textArea, dense);
}

export function registerPlatformVoice(register) {
    register('VoiceInput', (host, component) => renderVoiceInput(host, component));
}
