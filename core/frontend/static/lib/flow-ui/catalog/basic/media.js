import { html } from '../../../lit-shim.js';
import {
    optionalComponentProperty,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';
import { flowUIText } from '../../utils/text.js';

function mediaSrc(host, component) {
    const bound = resolveBound(host.surface, component, 'src', host.tasks);
    const value = bound ?? optionalComponentProperty(component, 'src');
    if (value == null || String(value).trim() === '') {
        throw new Error(`flow-ui: ${component.type} ${component.component_id} requires src`);
    }
    return String(value);
}

function imageSrc(host, component) {
    const bound = resolveBound(host.surface, component, 'src', host.tasks);
    const value = bound ?? optionalComponentProperty(component, 'src');
    if (value == null || String(value).trim() === '') {
        return null;
    }
    return String(value);
}

export function renderImage(host, component) {
    const alt = optionalComponentProperty(component, 'alt');
    const src = imageSrc(host, component);
    if (src === null) {
        const label = alt == null || String(alt).trim() === ''
            ? flowUIText(host.locale, 'image_empty')
            : String(alt);
        return wrapFlowNode(
            host,
            component,
            html`<div class="image-empty" role="img" aria-label=${label}>${flowUIText(host.locale, 'image_empty')}</div>`,
        );
    }
    return wrapFlowNode(
        host,
        component,
        html`<img src=${src} alt=${alt == null ? '' : String(alt)}>`,
    );
}

export function renderVideo(host, component) {
    return wrapFlowNode(
        host,
        component,
        html`<video controls src=${mediaSrc(host, component)}></video>`,
    );
}

export function renderAudioPlayer(host, component) {
    return wrapFlowNode(
        host,
        component,
        html`<audio controls src=${mediaSrc(host, component)}></audio>`,
    );
}

export function registerBasicMedia(register) {
    register('Image', renderImage);
    register('Video', renderVideo);
    register('AudioPlayer', renderAudioPlayer);
}
