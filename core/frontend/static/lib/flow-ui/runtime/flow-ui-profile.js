import { interfaceProfileUrl } from '../protocol/a2a-codec.js';
import { LINNEX_CATALOG_ID } from '../protocol/constants.js';

export const FLOW_UI_PROFILE_KINDS = Object.freeze([
    'spa', 'editor_test', 'embed_public', 'embed_preview', 'operator_handoff',
]);

export async function fetchFlowUIProfile({ target, headers = {}, credentials = 'include', signal }) {
    const response = await fetch(interfaceProfileUrl(target), {
        headers: { Accept: 'application/json', ...headers },
        credentials,
        signal,
    });
    if (!response.ok) throw new Error(`flow-ui profile: HTTP ${response.status}`);
    const profile = await response.json();
    if (!profile?.viewer || !profile?.capabilities || !profile?.catalog) {
        throw new Error('flow-ui profile: malformed control-plane response');
    }
    if (profile.catalog.platform_catalog_id !== LINNEX_CATALOG_ID) {
        throw new Error('flow-ui profile: unsupported platform catalog');
    }
    if ('document' in profile || 'values' in profile || 'artifacts' in profile) {
        throw new Error('flow-ui profile: runtime state leaked into control plane');
    }
    return Object.freeze(profile);
}

export function createLocalFlowUIProfile(kind = 'editor_test') {
    if (!FLOW_UI_PROFILE_KINDS.includes(kind)) throw new Error(`Unknown Flow UI profile ${kind}`);
    // editor_test runs in production iframe without PlatformApp factories —
    // voice chrome requires platform/voice_dictation and must stay off.
    const voice = kind !== 'editor_test';
    return Object.freeze({
        viewer: Object.freeze({
            can_edit_flow: kind === 'editor_test',
            can_interact: true,
            can_share: false,
            auth_mode: 'platform',
        }),
        look: null,
        catalog: Object.freeze({ platform_catalog_id: LINNEX_CATALOG_ID, version: 'v0.9.1' }),
        capabilities: Object.freeze({
            bootstrap: false,
            autosync: false,
            cancel: true,
            files: true,
            voice,
        }),
        flow_identity: Object.freeze({ title: 'Flow UI', image_url: null }),
    });
}

/**
 * Live Test run (`profile="editor_test"` without initialDocument) still bootstraps over A2A,
 * but must not debounce-sync on every keystroke — only submit (after flush) hits the network
 * for values. Production SPA/embed keep server-declared autosync.
 */
export function applyFlowUIProfileKindOverrides(profile, profileKind) {
    if (!profile || typeof profile !== 'object' || !profile.capabilities) {
        throw new Error('flow-ui profile override requires a loaded profile');
    }
    if (typeof profileKind !== 'string' || profileKind.trim() === '') {
        throw new Error('flow-ui profile override requires profileKind');
    }
    if (profileKind !== 'editor_test') return profile;
    if (profile.capabilities.autosync === false) return profile;
    return Object.freeze({
        ...profile,
        capabilities: Object.freeze({
            ...profile.capabilities,
            autosync: false,
        }),
    });
}
