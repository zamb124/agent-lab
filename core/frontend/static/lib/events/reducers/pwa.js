/**
 * PWA slice.
 *
 * Поля state.pwa:
 *   pushPermission:    'default' | 'granted' | 'denied'
 *   pushRegistered:    boolean
 *   pushEndpoint:      string|null
 *   installAvailable:  boolean
 *   installed:         boolean
 *   updateAvailable:   boolean
 *   deploymentVersion: string|null
 */

import { CoreEvents } from '../contract.js';
import { PWA_EVENTS } from '../effects/pwa.effect.js';

export const initialPwaState = Object.freeze({
    pushPermission: 'default',
    pushRegistered: false,
    pushEndpoint: null,
    installAvailable: false,
    installed: false,
    updateAvailable: false,
    deploymentVersion: null,
});

export function pwaReducer(state = initialPwaState, event) {
    switch (event.type) {
        case CoreEvents.PWA_PUSH_PERMISSION_REQUESTED: {
            const perm = event.payload && event.payload.permission;
            if (perm !== 'default' && perm !== 'granted' && perm !== 'denied') return state;
            return state.pushPermission === perm ? state : { ...state, pushPermission: perm };
        }
        case CoreEvents.PWA_PUSH_REGISTERED: {
            const endpoint = event.payload && event.payload.endpoint;
            return { ...state, pushRegistered: true, pushEndpoint: endpoint || state.pushEndpoint };
        }
        case PWA_EVENTS.PUSH_UNSUBSCRIBED:
            return { ...state, pushRegistered: false, pushEndpoint: null };
        case CoreEvents.PWA_INSTALL_AVAILABLE:
            return state.installAvailable ? state : { ...state, installAvailable: true };
        case CoreEvents.PWA_INSTALLED:
            return state.installed ? state : { ...state, installed: true, installAvailable: false };
        case CoreEvents.PWA_UPDATE_AVAILABLE:
            return state.updateAvailable ? state : { ...state, updateAvailable: true };
        case PWA_EVENTS.DEPLOYMENT_VERSION_LOADED: {
            const version = event.payload && event.payload.version;
            if (!version || version === state.deploymentVersion) return state;
            return { ...state, deploymentVersion: version };
        }
        default:
            return state;
    }
}
