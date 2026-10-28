/**
 * Копирование текста в буфер обмена.
 * Clipboard API отсутствует на HTTP вне localhost — тогда используется textarea + execCommand; отказ API пробрасывается.
 */

/**
 * @param {string} text
 * @returns {Promise<void>}
 */
export async function copyTextToClipboard(text: string): Promise<void> {
    if (typeof text !== 'string') {
        throw new TypeError('copyTextToClipboard: ожидается строка');
    }

    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, text.length);

    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);

    if (!ok) {
        throw new Error('execCommand(copy) не удалось выполнить');
    }
}
