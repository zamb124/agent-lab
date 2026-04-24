/**
 * Frontend Service UI — entry point.
 *
 * Bootstrap корневого компонента; страницы/модалки/секции лендинга подключаются
 * транзитивно через `frontend-app.js`.
 */

import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-textarea.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-shell-page.js';
import '@platform/lib/components/pwa-install-banner.js';
import '@platform/lib/components/auth-modal.js';
import '@platform/lib/components/company-modal.js';
import '@platform/lib/components/glass-toast.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-modal-stack.js';

import './modals/lead-form-modal.js';
import './modals/create-api-key-modal.js';
import './modals/edit-api-key-modal.js';
import './modals/create-embed-modal.js';
import './modals/embed-code-modal.js';
import './modals/create-scheduler-task-modal.js';
import './modals/topup-modal.js';
import './modals/system-access-modal.js';
import './modals/balance-grant-modal.js';

import './components/landing/landing-header.js';
import './components/landing/landing-hero.js';
import './components/landing/landing-about.js';
import './components/landing/landing-abilities.js';
import './components/landing/landing-advantages.js';
import './components/landing/landing-plans.js';
import './components/landing/landing-reviews.js';
import './components/landing/landing-faq.js';
import './components/landing/landing-cta.js';
import './components/landing/landing-footer.js';

import './app/frontend-app.js';
