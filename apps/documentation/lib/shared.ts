export const appName = 'Humanitec';

/** Совпадает с `basePath` в next.config.mjs и с монтированием FastAPI на `/documentation/`. */
export const docPublicBasePath = '/documentation';

/**
 * Путь приложения внутри Next (корень app router). Публичный префикс задаётся только `basePath`
 * в next.config.mjs (`/documentation`). Если продублировать его здесь, ссылки станут
 * `/documentation/documentation/...`.
 */
export const docsRoute = '/';
