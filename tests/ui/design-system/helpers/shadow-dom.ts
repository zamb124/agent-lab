/** Shadow DOM helpers for UI Kit WTR contract tests. */

export function shadowQuery<T extends Element = HTMLElement>(host: Element, selector: string): T {
    const root = host.shadowRoot;
    if (!root) {
        throw new Error('shadowQuery: host shadowRoot missing');
    }
    const node = root.querySelector(selector);
    if (!node) {
        throw new Error(`shadowQuery: selector not found: ${selector}`);
    }
    return node as T;
}

export function shadowQueryAll<T extends Element = HTMLElement>(host: Element, selector: string): T[] {
    const root = host.shadowRoot;
    if (!root) {
        throw new Error('shadowQueryAll: host shadowRoot missing');
    }
    return [...root.querySelectorAll(selector)] as T[];
}
