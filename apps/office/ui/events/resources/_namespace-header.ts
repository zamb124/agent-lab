/**
 * Office BFF требует заголовок `X-Platform-Namespace` на все запросы под
 * `/documents/api/v1`. Каталоги и документы жёстко привязаны к namespace,
 * режим «все пространства» в Документах запрещён — `office-sidebar`
 * автоматически выбирает первый namespace, если выбора ещё нет.
 *
 * Реализация общая с другими сервисами (`core/.../platform-namespace-header.js`);
 * здесь остаётся только привычное для Office имя.
 */

export { platformNamespaceHeader as nsHeader } from '@platform/lib/utils/platform-namespace-header.js';
