/**
 * Versioned starter templates for one Flow UI page (surface).
 * Applying a template replaces the components and data model of the active
 * page; every template ships a reachable `platform.ui.submit` control so the
 * publish gate stays satisfiable out of the box.
 */
import { assistantWithSidebarSurface, chatSurface } from './pages/chat.js';
import { blankSurface } from './pages/blank.js';
import { contactSurface } from './pages/contact.js';
import { dashboardSurface } from './pages/dashboard.js';
import { eventDetailSurface } from './pages/event-detail.js';
import { leadFormSurface } from './pages/lead-form.js';
import { loginSurface } from './pages/login.js';
import { notificationCenterSurface } from './pages/notification-center.js';
import { productDetailSurface } from './pages/product-detail.js';
import { purchaseCompleteSurface } from './pages/purchase-complete.js';
import { statsOverviewSurface } from './pages/stats-overview.js';
import { statusTrackerSurface } from './pages/status-tracker.js';
import { taskListSurface } from './pages/task-list.js';
import { userProfileSurface } from './pages/user-profile.js';
import { validatedFormSurface } from './pages/validated-form.js';

/** @typedef {'conversation' | 'forms' | 'dashboards' | 'content' | 'utility'} FlowUIPageTemplateCategory */

/**
 * Closed set of gallery categories (order = chip order).
 * @type {readonly FlowUIPageTemplateCategory[]}
 */
export const FLOW_UI_PAGE_TEMPLATE_CATEGORIES = Object.freeze([
    'conversation',
    'forms',
    'dashboards',
    'content',
    'utility',
]);

/**
 * @type {readonly {
 *   template_id: string,
 *   version: string,
 *   icon: string,
 *   category: FlowUIPageTemplateCategory,
 *   tags: readonly string[],
 *   title: {ru: string, en: string},
 *   description: {ru: string, en: string},
 *   buildSurface: (surfaceId: string, locale: 'ru' | 'en') => object,
 * }[]}
 */
export const FLOW_UI_PAGE_TEMPLATES = Object.freeze([
    Object.freeze({
        template_id: 'linnex.page.chat',
        version: '1.0.0',
        icon: 'chat',
        category: 'conversation',
        tags: Object.freeze(['chat', 'composer', 'agent']),
        title: Object.freeze({ ru: 'Агентский чат', en: 'Agent chat' }),
        description: Object.freeze({
            ru: 'Лента диалога, приветствие, подсказки и композер с файлами и голосом.',
            en: 'Conversation feed, greeting, prompts and a composer with files and voice.',
        }),
        buildSurface: chatSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.assistant_context',
        version: '1.0.0',
        icon: 'layers',
        category: 'conversation',
        tags: Object.freeze(['chat', 'context', 'sidebar']),
        title: Object.freeze({ ru: 'Чат с контекстом', en: 'Chat with context' }),
        description: Object.freeze({
            ru: 'Диалог плюс блок контекста над лентой — для рабочих ассистентов.',
            en: 'Conversation plus a context block above the feed for work assistants.',
        }),
        buildSurface: assistantWithSidebarSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.lead_form',
        version: '1.0.0',
        icon: 'checklist',
        category: 'forms',
        tags: Object.freeze(['form', 'lead', 'request']),
        title: Object.freeze({ ru: 'Заявка', en: 'Request form' }),
        description: Object.freeze({
            ru: 'Заголовок, описание и форма заявки: имя, email, сообщение.',
            en: 'Headline, description and a request form: name, email, message.',
        }),
        buildSurface: leadFormSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.login',
        version: '1.0.0',
        icon: 'lock',
        category: 'forms',
        tags: Object.freeze(['form', 'auth', 'login']),
        title: Object.freeze({ ru: 'Вход', en: 'Login form' }),
        description: Object.freeze({
            ru: 'Экран входа: email, пароль и кнопка Submit.',
            en: 'Sign-in screen: email, password and Submit.',
        }),
        buildSurface: loginSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.contact',
        version: '1.0.0',
        icon: 'users',
        category: 'forms',
        tags: Object.freeze(['form', 'contact', 'card']),
        title: Object.freeze({ ru: 'Контакт', en: 'Contact card' }),
        description: Object.freeze({
            ru: 'Карточка контакта с аватаром и форма сообщения.',
            en: 'Contact card with avatar and a message form.',
        }),
        buildSurface: contactSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.validated_form',
        version: '1.0.0',
        icon: 'check-square',
        category: 'forms',
        tags: Object.freeze(['form', 'validation', 'required']),
        title: Object.freeze({ ru: 'Форма с валидацией', en: 'Validated form' }),
        description: Object.freeze({
            ru: 'Форма с checks required — Submit блокируется на пустых полях.',
            en: 'Form with required checks — Submit blocked on empty fields.',
        }),
        buildSurface: validatedFormSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.dashboard',
        version: '1.0.0',
        icon: 'chart',
        category: 'dashboards',
        tags: Object.freeze(['dashboard', 'metrics', 'table']),
        title: Object.freeze({ ru: 'Дашборд', en: 'Dashboard' }),
        description: Object.freeze({
            ru: 'Метрики в сетке 12 колонок, таблица данных и кнопка обновления.',
            en: 'Metrics on a 12-column grid, a data table and a refresh action.',
        }),
        buildSurface: dashboardSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.stats_overview',
        version: '1.0.0',
        icon: 'target',
        category: 'dashboards',
        tags: Object.freeze(['stats', 'metrics', 'alert']),
        title: Object.freeze({ ru: 'Статистика', en: 'Stats overview' }),
        description: Object.freeze({
            ru: 'Метрики, статус, прогресс и alert — обзор за сутки.',
            en: 'Metrics, status, progress and alert — 24h overview.',
        }),
        buildSurface: statsOverviewSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.task_list',
        version: '1.0.0',
        icon: 'list-check',
        category: 'dashboards',
        tags: Object.freeze(['tasks', 'cards', 'status']),
        title: Object.freeze({ ru: 'Список задач', en: 'Task list' }),
        description: Object.freeze({
            ru: 'Карточки задач с badge/status и обновлением списка.',
            en: 'Task cards with badge/status and a refresh action.',
        }),
        buildSurface: taskListSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.status_tracker',
        version: '1.0.0',
        icon: 'workflow',
        category: 'dashboards',
        tags: Object.freeze(['shipping', 'progress', 'status']),
        title: Object.freeze({ ru: 'Трекер статуса', en: 'Status tracker' }),
        description: Object.freeze({
            ru: 'Прогресс доставки и шаги статуса с обновлением.',
            en: 'Shipping progress and status steps with refresh.',
        }),
        buildSurface: statusTrackerSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.product_detail',
        version: '1.0.0',
        icon: 'box',
        category: 'content',
        tags: Object.freeze(['product', 'commerce', 'cta']),
        title: Object.freeze({ ru: 'Карточка продукта', en: 'Product detail' }),
        description: Object.freeze({
            ru: 'Изображение, цена, описание и CTA покупки.',
            en: 'Image, price, description and buy CTA.',
        }),
        buildSurface: productDetailSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.purchase_complete',
        version: '1.0.0',
        icon: 'check',
        category: 'content',
        tags: Object.freeze(['success', 'commerce', 'receipt']),
        title: Object.freeze({ ru: 'Покупка завершена', en: 'Purchase complete' }),
        description: Object.freeze({
            ru: 'Экран успеха с квитанцией и действиями.',
            en: 'Success screen with receipt and follow-up actions.',
        }),
        buildSurface: purchaseCompleteSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.user_profile',
        version: '1.0.0',
        icon: 'avatar',
        category: 'content',
        tags: Object.freeze(['profile', 'form', 'avatar']),
        title: Object.freeze({ ru: 'Профиль', en: 'User profile' }),
        description: Object.freeze({
            ru: 'Аватар и форма профиля с сохранением.',
            en: 'Avatar and profile form with save.',
        }),
        buildSurface: userProfileSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.event_detail',
        version: '1.0.0',
        icon: 'calendar',
        category: 'content',
        tags: Object.freeze(['event', 'rsvp', 'date']),
        title: Object.freeze({ ru: 'Событие', en: 'Event detail' }),
        description: Object.freeze({
            ru: 'Детали события и форма RSVP с датой.',
            en: 'Event details and RSVP form with date picker.',
        }),
        buildSurface: eventDetailSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.notification_center',
        version: '1.0.0',
        icon: 'bell-ring',
        category: 'content',
        tags: Object.freeze(['notifications', 'alerts', 'inbox']),
        title: Object.freeze({ ru: 'Уведомления', en: 'Notification center' }),
        description: Object.freeze({
            ru: 'Лента уведомлений с badge/alert и действиями.',
            en: 'Notification feed with badges, alerts and actions.',
        }),
        buildSurface: notificationCenterSurface,
    }),
    Object.freeze({
        template_id: 'linnex.page.blank',
        version: '1.0.0',
        icon: 'square',
        category: 'utility',
        tags: Object.freeze(['blank', 'empty']),
        title: Object.freeze({ ru: 'Пустая страница', en: 'Blank page' }),
        description: Object.freeze({
            ru: 'Только PageShell, заголовок и Submit — начните с нуля.',
            en: 'Just a PageShell, a heading and Submit — start from scratch.',
        }),
        buildSurface: blankSurface,
    }),
]);

export function flowUIPageTemplate(templateId) {
    const template = FLOW_UI_PAGE_TEMPLATES.find((item) => item.template_id === templateId);
    if (!template) {
        throw new Error(`flow-ui: unknown page template ${templateId}`);
    }
    return template;
}

/**
 * Filter gallery templates by category and free-text query (title/description/tags).
 * @param {{
 *   category?: FlowUIPageTemplateCategory | 'all',
 *   query?: string,
 *   locale?: 'ru' | 'en',
 * }} [options]
 */
export function filterFlowUIPageTemplates(options = {}) {
    const category = options.category || 'all';
    const locale = options.locale === 'ru' ? 'ru' : 'en';
    const query = typeof options.query === 'string' ? options.query.trim().toLowerCase() : '';
    return FLOW_UI_PAGE_TEMPLATES.filter((template) => {
        if (category !== 'all' && template.category !== category) {
            return false;
        }
        if (!query) {
            return true;
        }
        const haystack = [
            template.title[locale],
            template.description[locale],
            template.template_id,
            ...template.tags,
        ].join(' ').toLowerCase();
        return haystack.includes(query);
    });
}
