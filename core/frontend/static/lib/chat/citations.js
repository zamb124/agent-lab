/**
 * Инлайн-цитаты вида `[1]`, `[2]` в готовом HTML ответа ассистента.
 *
 * Работает поверх результата `flowsChatMarkdownToHtml`: находит только числовые
 * токены `[N]` в текстовых сегментах (вне тегов `<a>`, `<code>`, `<pre>` и вне
 * самих тегов) и заменяет их на кликабельные суперскрипт-ссылки. `resolve(index)`
 * возвращает `{ url, label }` для валидного источника или `null` — тогда токен
 * остаётся как есть.
 */

function _escapeAttribute(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

const _CITATION_SKIP_OPEN = /^<(a|code|pre)\b/i;
const _CITATION_SKIP_CLOSE = /^<\/(a|code|pre)\s*>/i;
const _CITATION_TOKEN = /\[(\d{1,2})\]/g;

/**
 * @param {string} html — HTML-фрагмент ответа (после markdown).
 * @param {(index: number) => ({ url: string, label: string } | null)} resolve
 * @returns {string}
 */
export function applyInlineCitations(html, resolve) {
    if (typeof html !== 'string' || html === '') {
        return '';
    }
    if (typeof resolve !== 'function') {
        throw new Error('applyInlineCitations: resolve must be a function');
    }
    const segments = html.split(/(<[^>]+>)/g);
    let skipDepth = 0;
    const out = [];
    for (const segment of segments) {
        if (segment === '') {
            continue;
        }
        if (segment.charCodeAt(0) === 60) {
            if (_CITATION_SKIP_CLOSE.test(segment)) {
                if (skipDepth > 0) {
                    skipDepth -= 1;
                }
            } else if (_CITATION_SKIP_OPEN.test(segment) && !segment.endsWith('/>')) {
                skipDepth += 1;
            }
            out.push(segment);
            continue;
        }
        if (skipDepth > 0) {
            out.push(segment);
            continue;
        }
        out.push(segment.replace(_CITATION_TOKEN, (match, digits) => {
            const index = Number(digits);
            const ref = resolve(index);
            if (ref === null) {
                return match;
            }
            const url = _escapeAttribute(ref.url);
            const label = _escapeAttribute(ref.label);
            return `<a class="answer-citation" href="${url}" target="_blank" rel="noopener noreferrer" data-citation="${index}" title="${label}">${index}</a>`;
        }));
    }
    return out.join('');
}
