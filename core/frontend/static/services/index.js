/**
 * Централизованный экспорт всех сервисов
 * 
 * Использует ServiceRegistry для автоматической регистрации
 * Сервисы регистрируются при инициализации приложения через PlatformApp.initServices()
 */
export { ServiceRegistry, Services } from '../lib/services/ServiceRegistry.js';
export { AuthService } from './auth.service.js';
export { ThemeService } from './theme.service.js';
export { NotifyService } from './notify.service.js';
export { IconService } from './icon.service.js';
export { CompaniesService } from './companies.service.js';
export { CalendarService } from './calendar.service.js';
export { FilesService } from './files.service.js';

