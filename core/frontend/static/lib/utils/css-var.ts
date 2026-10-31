/**
 * Резолв CSS-переменной из documentElement для canvas/chart контекстов,
 * где var(--x) строкой недопустим (ctx.fillStyle, palette данные).
 *
 * tokens.css гарантирует наличие DS-токенов; fallback — доменное значение
 * для сред без загруженной темы (embed, тесты).
 */
export function cssVar(name: string, fallback: string): string {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value.length > 0 ? value : fallback;
}
