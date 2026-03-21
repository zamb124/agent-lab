/**
 * Platform Management - Entry Point
 */

console.log('🚀 Platform Management загружается...');

// Импортируем главное приложение - оно автоматически инициализирует все сервисы
import './app/FrontendApp.js';

// Импортируем sidebar
import './components/frontend-sidebar.js';

// Импортируем core компоненты
import '@platform/lib/components/platform-user.js';

// Импортируем страницы
import './pages/landing-page.js';
import './pages/select-company-page.js';
import './pages/join-page.js';
import './pages/dashboard-page.js';
import './pages/team/team-page.js';
import './pages/api-keys/api-keys-page.js';
import './pages/billing/billing-page.js';
import './pages/embed-configs-page.js';
import './pages/settings/settings-page.js';

// Страницы продуктов
import './pages/products/product-agents-page.js';
import './pages/products/product-rag-page.js';
import './pages/products/product-crm-page.js';

// Импортируем компоненты лендинга
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

console.log('✅ Platform Management инициализирован');
