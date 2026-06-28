/**
 * На mobile поднимает focused input в видимую область visualViewport (клавиатура iOS/Android).
 */

const MOBILE_SHELL_MQ = '(max-width: 767px)';

/** @typedef {{ block?: 'nearest' | 'center' }} EnsureInputVisibleOptions */

/**
 * @param {HTMLElement} inputEl
 * @returns {boolean}
 */
function isElementVerticallyVisibleInVisualViewport(inputEl) {
    const vv = window.visualViewport;
    if (!vv || typeof vv.height !== 'number') {
        return true;
    }
    const rect = inputEl.getBoundingClientRect();
    const visibleTop = vv.offsetTop;
    const visibleBottom = vv.offsetTop + vv.height;
    const edgeInset = 8;
    return rect.top >= visibleTop + edgeInset && rect.bottom <= visibleBottom - edgeInset;
}

/**
 * @param {HTMLElement} node
 * @returns {HTMLElement | null}
 */
function findScrollableAncestor(node) {
    let current = node.parentElement;
    while (current !== null) {
        const style = window.getComputedStyle(current);
        const overflowY = style.overflowY;
        if (
            (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay')
            && current.scrollHeight > current.clientHeight
        ) {
            return current;
        }
        current = current.parentElement;
    }
    return null;
}

/**
 * @param {HTMLElement} scrollContainer
 * @param {HTMLElement} inputEl
 * @param {'nearest' | 'center'} block
 */
function scrollContainerToRevealInput(scrollContainer, inputEl, block) {
    const containerRect = scrollContainer.getBoundingClientRect();
    const inputRect = inputEl.getBoundingClientRect();
    const edgeInset = 12;
    const visibleHeight = scrollContainer.clientHeight;
    const inputOffsetInContainer = inputRect.top - containerRect.top + scrollContainer.scrollTop;

    let targetScrollTop = scrollContainer.scrollTop;
    if (block === 'center') {
        targetScrollTop = inputOffsetInContainer - visibleHeight / 2 + inputRect.height / 2;
    } else if (inputRect.top < containerRect.top + edgeInset) {
        targetScrollTop = inputOffsetInContainer - edgeInset;
    } else if (inputRect.bottom > containerRect.bottom - edgeInset) {
        targetScrollTop = inputOffsetInContainer - visibleHeight + inputRect.height + edgeInset;
    }

    const maxScrollTop = scrollContainer.scrollHeight - visibleHeight;
    const clampedScrollTop = Math.max(0, Math.min(targetScrollTop, maxScrollTop));
    if (Math.abs(clampedScrollTop - scrollContainer.scrollTop) < 1) {
        return;
    }
    scrollContainer.scrollTo({ top: clampedScrollTop, behavior: 'instant' });
}

/**
 * @param {HTMLElement} inputEl
 * @param {'nearest' | 'center'} block
 */
function scrollWindowToRevealInput(inputEl, block) {
    const vv = window.visualViewport;
    if (!vv || typeof vv.height !== 'number') {
        inputEl.scrollIntoView({ block, behavior: 'instant' });
        return;
    }
    const rect = inputEl.getBoundingClientRect();
    const edgeInset = 12;
    const visibleTop = vv.offsetTop;
    const visibleBottom = vv.offsetTop + vv.height;
    let deltaY = 0;
    if (block === 'center') {
        const targetTop = visibleTop + (vv.height - rect.height) / 2;
        deltaY = rect.top - targetTop;
    } else if (rect.top < visibleTop + edgeInset) {
        deltaY = rect.top - (visibleTop + edgeInset);
    } else if (rect.bottom > visibleBottom - edgeInset) {
        deltaY = rect.bottom - (visibleBottom - edgeInset);
    }
    if (Math.abs(deltaY) < 1) {
        return;
    }
    window.scrollBy({ top: deltaY, left: 0, behavior: 'instant' });
}

/**
 * @param {HTMLElement} inputEl
 * @param {EnsureInputVisibleOptions} [options]
 */
export function ensureInputVisibleInVisualViewport(inputEl, options) {
    if (typeof window === 'undefined') {
        return;
    }
    if (!(inputEl instanceof HTMLElement)) {
        return;
    }
    const mq = window.matchMedia(MOBILE_SHELL_MQ);
    if (!mq.matches) {
        return;
    }
    const block = options && options.block === 'center' ? 'center' : 'nearest';
    if (isElementVerticallyVisibleInVisualViewport(inputEl)) {
        return;
    }
    const scrollContainer = findScrollableAncestor(inputEl);
    if (scrollContainer !== null) {
        scrollContainerToRevealInput(scrollContainer, inputEl, block);
        return;
    }
    scrollWindowToRevealInput(inputEl, block);
}

/**
 * @param {HTMLElement} inputEl
 * @param {EnsureInputVisibleOptions} [options]
 * @returns {() => void}
 */
export function bindInputVisibleInVisualViewport(inputEl, options) {
    if (typeof window === 'undefined') {
        return () => {};
    }
    if (!(inputEl instanceof HTMLElement)) {
        return () => {};
    }
    const mq = window.matchMedia(MOBILE_SHELL_MQ);
    if (!mq.matches) {
        return () => {};
    }

    const reveal = () => {
        if (document.activeElement !== inputEl) {
            return;
        }
        ensureInputVisibleInVisualViewport(inputEl, options);
    };

    const onFocus = () => {
        requestAnimationFrame(() => {
            requestAnimationFrame(reveal);
        });
    };

    inputEl.addEventListener('focus', onFocus);

    const vv = window.visualViewport;
    if (vv) {
        vv.addEventListener('resize', reveal);
        vv.addEventListener('scroll', reveal);
    }

    return () => {
        inputEl.removeEventListener('focus', onFocus);
        if (vv) {
            vv.removeEventListener('resize', reveal);
            vv.removeEventListener('scroll', reveal);
        }
    };
}
