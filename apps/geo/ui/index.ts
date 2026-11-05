/**
 * UI сервиса Geo — точка входа.
 *
 * Bootstrap корневого компонента и общих платформенных элементов. Все остальные
 * модули — страницы / компоненты / модалки — подключаются транзитивно через
 * `geo-app.js`.
 */

import '@platform/lib/utils/viewport-app-vh.js';
import '@platform/lib/utils/platform-deeplink-init.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/company-modal.js';

import './app/geo-app.js';
