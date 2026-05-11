/**
 * Однострочное подключение Lara на стороннем сайте: один <script type="module" src="...humanitec-embed-autoload.js" data-*></script>.
 * Import map не нужен — замыкание embed на относительных импортах до lit-shim (см. scripts/check_embed_esm_closure.py).
 *
 * Обязательно: data-embed-id, data-flows-base-url.
 * Опционально: data-platform-ui-origin — абсолютный origin платформы (i18n, file-types, SVG). Если CDN
 *   отделён от API, указывать обязательно (в коде из консоли он уже задаётся); иначе берётся origin скрипта.
 * Токен: POST на data-chat-token-url (default /api/chat-token) телом как в справке виджета.
 */

import './platform-lara-assistant.js';

/** @returns {HTMLScriptElement | null} */
function resolveHostScript() {
    const meta = typeof import.meta !== 'undefined' ? import.meta : null;
    if (meta && meta.scriptElement instanceof HTMLScriptElement) {
        return meta.scriptElement;
    }
    const needles = ['/humanitec-embed-autoload.js', 'humanitec-embed-autoload.js'];
    const list = typeof document !== 'undefined' ? document.querySelectorAll('script[src]') : [];
    for (let i = list.length - 1; i >= 0; i -= 1) {
        const s = list[i];
        if (!(s instanceof HTMLScriptElement)) continue;
        const src = typeof s.src === 'string' ? s.src : '';
        if (needles.some((n) => src.includes(n))) {
            return s;
        }
    }
    return null;
}

/**
 * @param {HTMLScriptElement} scriptEl
 * @returns {boolean}
 */
function readDatasetBool(scriptEl, camelKey, defaultValue) {
    if (!Object.prototype.hasOwnProperty.call(scriptEl.dataset, camelKey)) return defaultValue;
    const raw = scriptEl.dataset[camelKey];
    if (typeof raw !== 'string' || raw.trim() === '') return defaultValue;
    const v = raw.trim().toLowerCase();
    return v === '1' || v === 'true' || v === 'yes';
}

/**
 * @param {HTMLScriptElement} scriptEl
 * @param {DOMStringMap} ds
 */
function resolveEmbedPlatformUiOrigin(scriptEl, ds) {
    const explicit =
        typeof ds.platformUiOrigin === 'string' && ds.platformUiOrigin.trim() !== ''
            ? ds.platformUiOrigin.trim().replace(/\/+$/, '')
            : '';
    if (explicit !== '') {
        return explicit;
    }
    const srcRaw = typeof scriptEl.src === 'string' ? scriptEl.src.trim() : '';
    if (srcRaw !== '') {
        try {
            return new URL(srcRaw).origin;
        } catch (e) {
            const err = new Error(`humanitec-embed-autoload: invalid script src (${srcRaw})`);
            err.cause = e;
            throw err;
        }
    }
    return '';
}

/**
 * @param {HTMLScriptElement} scriptEl
 */
function mountFromScript(scriptEl) {
    const ds = scriptEl.dataset;
    const embedId = (ds.embedId || '').trim();
    if (!embedId) {
        throw new Error('humanitec-embed-autoload: data-embed-id required');
    }
    const flowsBaseUrl = (ds.flowsBaseUrl || '').trim();
    if (!flowsBaseUrl) {
        throw new Error('humanitec-embed-autoload: data-flows-base-url required');
    }

    const chatTokenUrlRaw = ds.chatTokenUrl;
    const chatTokenUrl =
        typeof chatTokenUrlRaw === 'string' && chatTokenUrlRaw.trim() !== ''
            ? chatTokenUrlRaw.trim()
            : '/api/chat-token';

    let expiresInSeconds = 300;
    if (typeof ds.tokenExpiresSeconds === 'string' && ds.tokenExpiresSeconds.trim() !== '') {
        const n = Number(ds.tokenExpiresSeconds);
        if (!Number.isFinite(n) || n <= 0) {
            throw new Error('humanitec-embed-autoload: data-token-expires-seconds must be positive number');
        }
        expiresInSeconds = n;
    }

    async function getEmbedToken() {
        const response = await fetch(chatTokenUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                embed_id: embedId,
                origin: typeof window !== 'undefined' ? window.location.origin : '',
                expires_in_seconds: expiresInSeconds,
            }),
        });
        if (!response.ok) {
            throw new Error('Cannot get embed session token');
        }
        const data = await response.json();
        const token =
            typeof data.token === 'string' && data.token !== ''
                ? data.token
                : (typeof data.access_token === 'string' ? data.access_token : '');
        if (!token) {
            throw new Error('humanitec-embed-autoload: token response missing token field');
        }
        return { Authorization: `Bearer ${token}` };
    }

    /** @type {HTMLElement} */
    const assistant = document.createElement('platform-lara-assistant');
    assistant.setAttribute('embed-id', embedId);
    if ((ds.flowId || '').trim() !== '') {
        assistant.setAttribute('flow-id', ds.flowId.trim());
    }

    const assistantTitle = typeof ds.assistantTitle === 'string' ? ds.assistantTitle.trim() : '';
    if (assistantTitle !== '') {
        assistant.setAttribute('assistant-title', assistantTitle);
    }

    const theme = typeof ds.theme === 'string' ? ds.theme.trim() : '';
    if (theme !== '') {
        assistant.setAttribute('theme', theme);
    }

    const locale = typeof ds.locale === 'string' ? ds.locale.trim() : '';
    if (locale !== '') {
        assistant.setAttribute('locale', locale);
    }

    const eventNs = typeof ds.eventNamespace === 'string' ? ds.eventNamespace.trim() : '';
    if (eventNs !== '') {
        assistant.setAttribute('event-namespace', eventNs);
    } else {
        assistant.setAttribute('event-namespace', 'assistant');
    }

    const toggleEvt = typeof ds.toggleEventName === 'string' ? ds.toggleEventName.trim() : '';
    assistant.setAttribute('toggle-event-name', toggleEvt !== '' ? toggleEvt : 'humanitec-embed-chat-toggle');

    assistant.useCredentials = readDatasetBool(scriptEl, 'useCredentials', false);
    assistant.showLauncher = readDatasetBool(scriptEl, 'showLauncher', false);

    assistant.flowsBaseUrl = flowsBaseUrl;

    const platformUiOrigin = resolveEmbedPlatformUiOrigin(scriptEl, ds);
    if (platformUiOrigin !== '') {
        assistant.setAttribute('platform-ui-origin', platformUiOrigin);
    }

    const voiceBaseUrl = typeof ds.voiceBaseUrl === 'string' ? ds.voiceBaseUrl.trim() : '';
    if (voiceBaseUrl !== '') {
        assistant.setAttribute('voice-base-url', voiceBaseUrl);
    }

    assistant.voiceEnabled = readDatasetBool(scriptEl, 'voiceEnabled', false);
    assistant.voiceDefaultOn = readDatasetBool(scriptEl, 'voiceDefaultOn', false);

    const companyId = typeof ds.companyId === 'string' ? ds.companyId.trim() : '';
    if (companyId !== '') {
        assistant.setAttribute('company-id', companyId);
    }

    assistant.getAuthToken = getEmbedToken;

    assistant.getExtraMetadataVariables = async () => ({
        page_url: typeof window !== 'undefined' ? window.location.href : '',
        page_title: typeof document !== 'undefined' ? document.title : '',
    });

    assistant.getContextVariables = async () => ({
        viewport_width: typeof window !== 'undefined' ? window.innerWidth : 0,
        viewport_height: typeof window !== 'undefined' ? window.innerHeight : 0,
    });

    if (typeof document.body === 'undefined' || document.body === null) {
        throw new Error('humanitec-embed-autoload: document.body required');
    }
    document.body.appendChild(assistant);

    window.humanitecEmbed = {
        element: assistant,
        setTheme(nextTheme) {
            assistant.setAttribute('theme', String(nextTheme));
        },
        setLocale(nextLocale) {
            assistant.setAttribute('locale', String(nextLocale));
        },
        setLauncherVisible(visible) {
            assistant.showLauncher = Boolean(visible);
        },
        setAssistantTitle(nextTitle) {
            assistant.setAttribute('assistant-title', String(nextTitle));
        },
        setFlowsBaseUrl(nextBaseUrl) {
            assistant.flowsBaseUrl = String(nextBaseUrl);
        },
        setEventNamespace(nextNamespace) {
            assistant.setAttribute('event-namespace', String(nextNamespace));
        },
        setToggleEventName(nextEventName) {
            assistant.setAttribute('toggle-event-name', String(nextEventName));
        },
        setMetadataHooks(extraMetadataProvider, contextProvider) {
            if (typeof extraMetadataProvider === 'function') {
                assistant.getExtraMetadataVariables = extraMetadataProvider;
            }
            if (typeof contextProvider === 'function') {
                assistant.getContextVariables = contextProvider;
            }
        },
        setAuthProvider(authProvider) {
            assistant.getAuthToken = authProvider;
        },
    };
}

function scheduleMount() {
    const scriptEl = resolveHostScript();
    if (!scriptEl) {
        throw new Error(
            'humanitec-embed-autoload: cannot resolve host script element (need import.meta.scriptElement or recognizable src)',
        );
    }

    function run() {
        mountFromScript(scriptEl);
    }

    if (typeof document !== 'undefined' && document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run, { once: true });
        return;
    }
    run();
}

scheduleMount();
