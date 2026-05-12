/**
 * RAG Service UI — entry point.
 *
 * Bootstrap корневого компонента и общих платформенных элементов. Все остальные
 * модули — страницы / компоненты / модалки — подключаются транзитивно через
 * `rag-app.js`.
 */

import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/company-modal.js';

import './app/rag-app.js';
