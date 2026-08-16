import { FLOW_UI_ACTIONS } from '../protocol/constants.js';

function isSubmitComponent(component) {
    const press = component?.actions?.press;
    return press?.kind === 'event' && press?.name === FLOW_UI_ACTIONS.submit;
}

function isMessageComposerComponent(component) {
    const presentation = component?.properties?.presentation;
    if (component?.type === 'Form' && presentation === 'composer') return true;
    if (component?.type === 'TextArea' && presentation === 'composer') return true;
    if (component?.properties?.formId === 'message-form') return true;
    return component?.component_id === 'message-form';
}

/**
 * Default chat (and any Interface with a conversation composer) has both a
 * message composer and platform.ui.submit. Custom forms may have Submit only.
 *
 * @param {unknown} document
 * @returns {boolean}
 */
export function flowUIDocumentHasMessageComposer(document) {
    if (!document || typeof document !== 'object') return false;
    const surfaces = document.surfaces;
    if (!surfaces || typeof surfaces !== 'object') return false;
    for (const surface of Object.values(surfaces)) {
        const components = surface && typeof surface === 'object' ? surface.components : null;
        if (!components || typeof components !== 'object') continue;
        let hasSubmit = false;
        let hasComposer = false;
        for (const component of Object.values(components)) {
            if (!component || typeof component !== 'object') continue;
            if (isSubmitComponent(component)) hasSubmit = true;
            if (isMessageComposerComponent(component)) hasComposer = true;
        }
        if (hasSubmit && hasComposer) return true;
    }
    return false;
}

/**
 * Keep operator-local field values when a live A2A ui.document snapshot arrives.
 * HITL send is REST, not A2A sync; live tail must not wipe the composer draft.
 *
 * @param {object | null | undefined} localDocument
 * @param {object} incomingDocument
 * @returns {object}
 */
export function overlayFlowUILocalValues(localDocument, incomingDocument) {
    if (!incomingDocument || typeof incomingDocument !== 'object') {
        throw new Error('overlayFlowUILocalValues: incoming document required');
    }
    const localSurfaces = localDocument && typeof localDocument === 'object'
        ? localDocument.surfaces
        : null;
    const incomingSurfaces = incomingDocument.surfaces;
    if (!localSurfaces || typeof localSurfaces !== 'object') {
        return incomingDocument;
    }
    if (!incomingSurfaces || typeof incomingSurfaces !== 'object') {
        return incomingDocument;
    }
    const nextSurfaces = { ...incomingSurfaces };
    let changed = false;
    for (const [surfaceId, localSurface] of Object.entries(localSurfaces)) {
        const incomingSurface = nextSurfaces[surfaceId];
        if (!incomingSurface || typeof incomingSurface !== 'object') continue;
        const localModel = localSurface && typeof localSurface === 'object'
            ? localSurface.data_model
            : null;
        const localValues = localModel && typeof localModel === 'object'
            ? localModel.values
            : null;
        if (!localValues || typeof localValues !== 'object') continue;
        const incomingModel = incomingSurface.data_model && typeof incomingSurface.data_model === 'object'
            ? incomingSurface.data_model
            : {};
        const incomingValues = incomingModel.values && typeof incomingModel.values === 'object'
            ? incomingModel.values
            : {};
        nextSurfaces[surfaceId] = {
            ...incomingSurface,
            data_model: {
                ...incomingModel,
                values: { ...incomingValues, ...localValues },
            },
        };
        changed = true;
    }
    if (!changed) return incomingDocument;
    return { ...incomingDocument, surfaces: nextSurfaces };
}
