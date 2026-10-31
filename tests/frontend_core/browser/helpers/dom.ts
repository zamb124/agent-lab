/**
 * DOM-фикстуры браузерных спеков: fail-closed доступ к shadow DOM и querySelector.
 */

export function shadow(el: Element): ShadowRoot {
    const root = el.shadowRoot;
    if (root === null) {
        throw new Error(`shadow: ${el.tagName} has no shadowRoot`);
    }
    return root;
}

/**
 * Граница DOM-фикстуры: компонентные члены и DOM-поля доступны через index signature.
 * Production-контракты не ослабляются — тип живёт только в браузерных спеках.
 */
export type TestEl = HTMLElement & { [key: string]: any };

export function qs<T extends Element = TestEl>(root: ParentNode, selector: string): T {
    const el = root.querySelector(selector);
    if (el === null) {
        throw new Error(`qs: no element for "${selector}"`);
    }
    return el as T;
}

export function q<T extends Element = TestEl>(root: ParentNode, selector: string): T | null {
    return root.querySelector(selector) as T | null;
}

export function qsa<T extends Element = TestEl>(root: ParentNode, selector: string): T[] {
    return Array.from(root.querySelectorAll(selector)) as T[];
}

const TOKENS_HREF = '/core/frontend/static/assets/css/tokens.css';

/**
 * Подключает tokens.css на страницу спека. Canon-спеки, измеряющие реальный CSS
 * (padding/height/overlap), обязаны грузить токены — иначе var(--space-*) не разрешены.
 */
export function ensureTokensLoaded(): Promise<void> {
    return new Promise<void>((resolve, reject) => {
        if (document.querySelector(`link[rel="stylesheet"][href="${TOKENS_HREF}"]`) !== null) {
            resolve();
            return;
        }
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = TOKENS_HREF;
        link.onload = () => resolve();
        link.onerror = () => reject(new Error(`tokens.css: ${TOKENS_HREF}`));
        document.head.appendChild(link);
    });
}
