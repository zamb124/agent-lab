/**
 * UI сервиса RAG — точка входа.
 *
 * Bootstrap корневого компонента и общих платформенных элементов. Все остальные
 * модули — страницы / компоненты / модалки — подключаются транзитивно через
 * `rag-app.js`.
 */

import '@platform/lib/utils/viewport-app-vh.js';
import '@platform/lib/utils/platform-deeplink-init.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/company-modal.js';

import './app/rag-app.js';

export { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
