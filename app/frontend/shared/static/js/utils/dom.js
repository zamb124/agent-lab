/**
 * Утилиты для работы с DOM
 */

export function createElement(tag, className = '', innerHTML = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (innerHTML) element.innerHTML = innerHTML;
    return element;
}

export function removeElement(element) {
    if (element && element.parentNode) {
        element.parentNode.removeChild(element);
    }
}

export function toggleClass(element, className) {
    if (!element) return;
    element.classList.toggle(className);
}

export function addClass(element, className) {
    if (!element) return;
    element.classList.add(className);
}

export function removeClass(element, className) {
    if (!element) return;
    element.classList.remove(className);
}

export function hasClass(element, className) {
    if (!element) return false;
    return element.classList.contains(className);
}

export function show(element) {
    if (element) element.style.display = 'block';
}

export function hide(element) {
    if (element) element.style.display = 'none';
}

export function fadeIn(element, duration = 300) {
    if (!element) return;
    element.style.opacity = '0';
    element.style.display = 'block';
    
    let start = null;
    const animate = (timestamp) => {
        if (!start) start = timestamp;
        const progress = timestamp - start;
        const opacity = Math.min(progress / duration, 1);
        element.style.opacity = opacity.toString();
        
        if (progress < duration) {
            requestAnimationFrame(animate);
        }
    };
    
    requestAnimationFrame(animate);
}

export function fadeOut(element, duration = 300) {
    if (!element) return;
    
    let start = null;
    const animate = (timestamp) => {
        if (!start) start = timestamp;
        const progress = timestamp - start;
        const opacity = 1 - Math.min(progress / duration, 1);
        element.style.opacity = opacity.toString();
        
        if (progress < duration) {
            requestAnimationFrame(animate);
        } else {
            element.style.display = 'none';
        }
    };
    
    requestAnimationFrame(animate);
}

export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export function escapeAttr(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;');
}

