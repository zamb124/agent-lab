import { docs } from 'collections/server';
import { loader } from 'fumadocs-core/source';
import { defineI18n } from 'fumadocs-core/i18n';
import { docsRoute } from './shared';

/**
 * i18n конфигурация для документации.
 * parser: 'dir' — ожидают структуру guides/{locale}/... и scenarios/{locale}/...
 * hideLocale: 'default-locale' — не показывать /ru/ в URL для locale по умолчанию.
 */
export const i18n = defineI18n({
  languages: ['ru', 'en'] as const,
  defaultLanguage: 'ru',
  parser: 'dir',
  hideLocale: 'default-locale',
  fallbackLanguage: 'ru',
});

export const source = loader({
  baseUrl: docsRoute,
  source: docs.toFumadocsSource(),
  i18n,
  plugins: [],
});
