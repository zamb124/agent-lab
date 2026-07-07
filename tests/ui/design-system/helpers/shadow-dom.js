/** Shadow DOM helpers for UI Kit WTR contract tests. */

export function shadowQuery(host, selector) {
    if (!host || !host.shadowRoot) {
        throw new Error('shadowQuery: host shadowRoot missing');
    }
    const node = host.shadowRoot.querySelector(selector);
    if (!node) {
        throw new Error(`shadowQuery: selector not found: ${selector}`);
    }
    return node;
}

export function shadowQueryAll(host, selector) {
    if (!host || !host.shadowRoot) {
        throw new Error('shadowQueryAll: host shadowRoot missing');
    }
    return [...host.shadowRoot.querySelectorAll(selector)];
}
