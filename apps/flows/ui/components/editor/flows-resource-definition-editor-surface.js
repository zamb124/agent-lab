/**
 * Редактор определения ресурса (каталог или ветка) по типу ResourceType.
 * Общий для flows-resource-property-panel и flows-resource-node-editor.
 */

import { html } from 'lit';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import '../resources/flows-base-resource-editor.js';
import '../resources/flows-llm-resource-editor.js';
import '../resources/flows-secret-resource-editor.js';
import '../resources/flows-code-resource-editor.js';
import '../resources/flows-http-resource-editor.js';
import '../resources/flows-files-resource-editor.js';
import '../resources/flows-prompt-resource-editor.js';
import '../resources/flows-rag-resource-editor.js';
import '../resources/flows-cache-resource-editor.js';

/**
 * @param {object} resource — view-model с resource_id, ?type, …
 * @param {(e: CustomEvent) => void} onChange — detail: { resourceId, patch }
 * @param {{ compactHeader?: boolean }} [options] — compactHeader: карточка на resource-ноде без описания/тегов
 */
export function renderResourceDefinitionEditor(resource, onChange, options = {}) {
    if (!isPlainObject(resource)) {
        return html``;
    }
    const id = typeof resource.resource_id === 'string' ? resource.resource_id : '';
    if (id.length === 0) {
        return html``;
    }
    const compactHeader = options.compactHeader === true;
    switch (resource.type) {
        case 'llm':
            return html`<flows-llm-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-llm-resource-editor>`;
        case 'secret':
            return html`<flows-secret-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-secret-resource-editor>`;
        case 'code':
            return html`<flows-code-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-code-resource-editor>`;
        case 'http':
            return html`<flows-http-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-http-resource-editor>`;
        case 'files':
            return html`<flows-files-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-files-resource-editor>`;
        case 'prompt':
            return html`<flows-prompt-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-prompt-resource-editor>`;
        case 'rag':
            return html`<flows-rag-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-rag-resource-editor>`;
        case 'cache':
            return html`<flows-cache-resource-editor .resourceId=${id} .resource=${resource}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-cache-resource-editor>`;
        default:
            return html`<flows-base-resource-editor .resourceId=${id} .resource=${resource}
                .resourceType=${asString(resource.type)}
                .compactHeader=${compactHeader}
                @change=${onChange}></flows-base-resource-editor>`;
    }
}
