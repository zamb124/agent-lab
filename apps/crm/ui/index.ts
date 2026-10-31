/**
 * CRM UI Entry Point
 */

import '@platform/lib/utils/viewport-app-vh.js';
import '@platform/lib/utils/platform-deeplink-init.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/company-modal.js';

import './app/crm-app.js';
import './components/crm-sidebar.js';

export { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
