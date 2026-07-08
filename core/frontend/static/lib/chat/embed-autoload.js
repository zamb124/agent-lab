/**
 * Однострочное подключение чат-виджета на стороннем сайте:
 * один <script type="module" src="...humanitec-embed-autoload.js" data-*></script>.
 * Import map не нужен — замыкание на относительных импортах до общего lib/lit-shim.js
 * (см. scripts/check_embed_esm_closure.py). Скрипт монтирует единый
 * `<platform-chat display="drawer" profile="embed_public">`.
 *
 * Обязательно: data-embed-id, data-flows-base-url.
 * Опционально: data-platform-ui-origin — абсолютный origin платформы (i18n, file-types, SVG).
 *   Если CDN отделён от API, указывать обязательно; иначе берётся origin скрипта.
 * data-initial-open="true" — открыть панель сразу при загрузке (guest preview и т.п.).
 * Токен: POST на data-chat-token-url (default /api/chat-token) телом как в справке виджета.
 */

import './platform-chat.js';
import { loadPlatformBrandBootstrap } from '../events/effects/platform-brand-bootstrap.js';

/**
 * @param {string} platformUiOrigin
 */
function ensureChatTokensStylesheet(platformUiOrigin) {
    const origin = typeof platformUiOrigin === 'string' ? platformUiOrigin.trim().replace(/\/+$/, '') : '';
    if (origin === '') {
        return;
    }
    if (document.querySelector('link[data-humanitec-chat-tokens="1"]')) {
        return;
    }
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `${origin}/static/core/lib/chat/chat-tokens.css`;
    link.setAttribute('data-humanitec-chat-tokens', '1');
    document.head.appendChild(link);
}

/** @returns {HTMLScriptElement | null} */
function resolveHostScript() {
    const meta = typeof import.meta !== 'undefined' ? import.meta : null;
    if (meta && meta.scriptElement instanceof HTMLScriptElement) {
        return meta.scriptElement;
    }
    const needles = ['/humanitec-embed-autoload.js', 'humanitec-embed-autoload.js', '/embed-autoload.js'];
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
async function mountFromScript(scriptEl) {
    const ds = scriptEl.dataset;
    const embedId = (ds.embedId || '').trim();
    if (!embedId) {
        throw new Error('humanitec-embed-autoload: data-embed-id required');
    }
    const flowsBaseUrl = (ds.flowsBaseUrl || '').trim();
    if (!flowsBaseUrl) {
        throw new Error('humanitec-embed-autoload: data-flows-base-url required');
    }

    const platformUiOrigin = resolveEmbedPlatformUiOrigin(scriptEl, ds);
    await loadPlatformBrandBootstrap({
        platformUiOrigin: platformUiOrigin !== '' ? platformUiOrigin : undefined,
    });

    const staticBearerRaw = typeof ds.staticBearer === 'string' ? ds.staticBearer.trim() : '';
    const staticBearer = staticBearerRaw;

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

    /** @type {() => Promise<{ Authorization?: string }>} */
    let getEmbedToken;
    if (staticBearer !== '') {
        getEmbedToken = async () => ({ Authorization: `Bearer ${staticBearer}` });
    } else {
        async function getEmbedTokenFetch() {
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
        getEmbedToken = getEmbedTokenFetch;
    }

    /** @type {HTMLElement} */
    const chat = document.createElement('platform-chat');
    chat.setAttribute('display', 'drawer');
    chat.setAttribute('profile', 'embed_public');
    chat.setAttribute('embed-id', embedId);
    if ((ds.flowId || '').trim() !== '') {
        chat.setAttribute('flow-id', ds.flowId.trim());
    }

    const branchId = typeof ds.branchId === 'string' ? ds.branchId.trim() : '';
    if (branchId !== '') {
        chat.setAttribute('branch-id', branchId);
    }

    const assistantTitle = typeof ds.assistantTitle === 'string' ? ds.assistantTitle.trim() : '';
    if (assistantTitle !== '') {
        chat.setAttribute('assistant-title', assistantTitle);
    }

    const theme = typeof ds.theme === 'string' ? ds.theme.trim() : '';
    if (theme !== '') {
        chat.setAttribute('theme', theme);
    }

    const locale = typeof ds.locale === 'string' ? ds.locale.trim() : '';
    if (locale !== '') {
        chat.setAttribute('interface-locale', locale);
    }

    const eventNs = typeof ds.eventNamespace === 'string' ? ds.eventNamespace.trim() : '';
    chat.setAttribute('event-namespace', eventNs !== '' ? eventNs : 'assistant');

    const toggleEvt = typeof ds.toggleEventName === 'string' ? ds.toggleEventName.trim() : '';
    chat.setAttribute('toggle-event-name', toggleEvt !== '' ? toggleEvt : 'humanitec-embed-chat-toggle');

    chat.useCredentials = readDatasetBool(scriptEl, 'useCredentials', false);
    chat.showLauncher = readDatasetBool(scriptEl, 'showLauncher', false);
    chat.initialOpen = readDatasetBool(scriptEl, 'initialOpen', false);
    if (chat.initialOpen) {
        chat.setAttribute('initial-open', '');
    }

    chat.flowsBaseUrl = flowsBaseUrl;

    ensureChatTokensStylesheet(platformUiOrigin);
    if (platformUiOrigin !== '') {
        chat.setAttribute('platform-ui-origin', platformUiOrigin);
    }

    const voiceBaseUrl = typeof ds.voiceBaseUrl === 'string' ? ds.voiceBaseUrl.trim() : '';
    if (voiceBaseUrl !== '') {
        chat.setAttribute('voice-base-url', voiceBaseUrl);
    }

    if (readDatasetBool(scriptEl, 'voiceEnabled', false)) {
        chat.setAttribute('voice-enabled', '');
    }
    if (readDatasetBool(scriptEl, 'voiceDefaultOn', false)) {
        chat.setAttribute('voice-default-on', '');
    }

    const companyId = typeof ds.companyId === 'string' ? ds.companyId.trim() : '';
    if (companyId !== '') {
        chat.setAttribute('company-id', companyId);
    }

    chat.getAuthToken = getEmbedToken;

    chat.getExtraMetadataVariables = async () => ({
        page_url: typeof window !== 'undefined' ? window.location.href : '',
        page_title: typeof document !== 'undefined' ? document.title : '',
    });

    chat.getContextVariables = async () => ({
        viewport_width: typeof window !== 'undefined' ? window.innerWidth : 0,
        viewport_height: typeof window !== 'undefined' ? window.innerHeight : 0,
    });

    if (typeof document.body === 'undefined' || document.body === null) {
        throw new Error('humanitec-embed-autoload: document.body required');
    }
    document.body.appendChild(chat);

    window.humanitecEmbed = {
        element: chat,
        setTheme(nextTheme) {
            chat.setAttribute('theme', String(nextTheme));
        },
        setLocale(nextLocale) {
            chat.setAttribute('interface-locale', String(nextLocale));
        },
        setLauncherVisible(visible) {
            chat.showLauncher = Boolean(visible);
        },
        setAssistantTitle(nextTitle) {
            chat.setAttribute('assistant-title', String(nextTitle));
        },
        setFlowsBaseUrl(nextBaseUrl) {
            chat.flowsBaseUrl = String(nextBaseUrl);
        },
        setEventNamespace(nextNamespace) {
            chat.setAttribute('event-namespace', String(nextNamespace));
        },
        setToggleEventName(nextEventName) {
            chat.setAttribute('toggle-event-name', String(nextEventName));
        },
        setMetadataHooks(extraMetadataProvider, contextProvider) {
            if (typeof extraMetadataProvider === 'function') {
                chat.getExtraMetadataVariables = extraMetadataProvider;
            }
            if (typeof contextProvider === 'function') {
                chat.getContextVariables = contextProvider;
            }
        },
        setAuthProvider(authProvider) {
            chat.getAuthToken = authProvider;
        },
    };
}

export { mountFromScript, resolveHostScript, readDatasetBool, ensureChatTokensStylesheet };

function scheduleMount() {
    const scriptEl = resolveHostScript();
    if (!scriptEl) {
        throw new Error(
            'humanitec-embed-autoload: cannot resolve host script element (need import.meta.scriptElement or recognizable src)',
        );
    }

    function run() {
        void mountFromScript(scriptEl);
    }

    if (typeof document !== 'undefined' && document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run, { once: true });
        return;
    }
    run();
}

const isVitestRuntime =
    (typeof import.meta !== 'undefined' &&
        import.meta.env &&
        String(import.meta.env.VITEST) === 'true') ||
    (typeof process !== 'undefined' && process.env.VITEST === 'true');

if (!isVitestRuntime) {
    scheduleMount();
}
