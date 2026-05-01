/**
 * Параметры виджета embed-чата из URL страницы (?embed_*=…).
 *
 * Имена (дубли — синонимы):
 * - embed_theme | embed-theme: light | dark | auto
 * - embed_lang | embed_locale | embed-lang | embed-locale: ru | en | auto
 * - embed_width | embed-panel-width: число (px) или CSS, например 420 или min(100vw-32px,520px)
 * - embed_max_height | embed-panel-max-height: число (px) или CSS
 * - embed_locale_control | embed-locale-control: 1 | 0 — показывать переключатель языка в композере
 * - embed_assistant_name | embed-assistant-name | embed_chat_title | embed-chat-title: подпись в шапке панели (имя ассистента), UTF-8 в query
 * - embed_branch | embed-branch | embed_branch_id | embed-branch-id: id ветки flow (например crm для Lara); уходит в metadata A2A как branch
 */

/**
 * @param {string} [search]
 * @returns {{
 *   theme?: string,
 *   locale?: string,
 *   panelWidth?: string,
 *   panelMaxHeight?: string,
 *   showLocaleControl?: boolean,
 *   assistantTitle?: string,
 *   branchId?: string,
 * }}
 */
function normalizeEmbedBranchId(raw) {
    if (raw == null) {
        return null;
    }
    const s = String(raw).trim();
    if (!s || s.length > 64) {
        return null;
    }
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(s)) {
        return null;
    }
    return s;
}

export function readEmbedChatUrlParams(search) {
    const raw =
        typeof search === 'string'
            ? search
            : typeof window !== 'undefined'
              ? window.location.search
              : '';
    const q = raw.startsWith('?') ? raw.slice(1) : raw;
    const sp = new URLSearchParams(q);

    const pick = (keys) => {
        for (const k of keys) {
            const v = sp.get(k);
            if (v != null && String(v).trim() !== '') {
                return String(v).trim();
            }
        }
        return null;
    };

    const out = {};

    const themeRaw = pick(['embed_theme', 'embed-theme']);
    if (themeRaw) {
        const t = themeRaw.toLowerCase();
        if (t === 'light' || t === 'dark' || t === 'auto') {
            out.theme = t;
        }
    }

    const langRaw = pick(['embed_lang', 'embed_locale', 'embed-lang', 'embed-locale']);
    if (langRaw) {
        const l = langRaw.toLowerCase();
        if (l === 'ru' || l === 'en' || l === 'auto') {
            out.locale = l;
        }
    }

    const w = pick(['embed_width', 'embed-panel-width']);
    if (w) {
        out.panelWidth = /^[\d.]+$/.test(w) ? `${w}px` : w;
    }

    const h = pick(['embed_max_height', 'embed-panel-max-height']);
    if (h) {
        out.panelMaxHeight = /^[\d.]+$/.test(h) ? `${h}px` : h;
    }

    const locCtl = pick(['embed_locale_control', 'embed-locale-control']);
    if (locCtl != null) {
        const v = locCtl.toLowerCase();
        out.showLocaleControl = v !== '0' && v !== 'false' && v !== 'no';
    }

    const assistantRaw = pick([
        'embed_assistant_name',
        'embed-assistant-name',
        'embed_chat_title',
        'embed-chat-title',
    ]);
    if (assistantRaw) {
        const trimmed = assistantRaw.replace(/\s+/g, ' ').trim();
        if (trimmed) {
            out.assistantTitle = trimmed.slice(0, 120);
        }
    }

    const branchRaw = pick(['embed_branch', 'embed-branch', 'embed_branch_id', 'embed-branch-id']);
    const mergedNorm = normalizeEmbedBranchId(branchRaw);
    if (mergedNorm) {
        out.branchId = mergedNorm;
    }

    return out;
}

/**
 * @param {HTMLElement} el — host drawer (style на элементе задаёт CSS-переменные для shadow)
 * @param {{ panelWidth?: string, panelMaxHeight?: string }} p
 */
export function applyEmbedChatDrawerSizeVars(el, p) {
    if (!el || !p) {
        return;
    }
    if (p.panelWidth) {
        el.style.setProperty('--embed-panel-width', p.panelWidth);
    }
    if (p.panelMaxHeight) {
        el.style.setProperty('--embed-panel-max-height', p.panelMaxHeight);
    }
}
