import type { TranslationsOption } from 'fumadocs-ui/contexts/i18n';

export type DocLocale = 'ru' | 'en';

export const DOC_LOCALE_STORAGE_KEY = 'humanitec-documentation-locale';

export const DOC_LOCALES: { name: string; locale: DocLocale }[] = [
  { name: 'Русский', locale: 'ru' },
  { name: 'English', locale: 'en' },
];

/**
 * Сохраняет предпочтительный язык в localStorage.
 * Fumadocs i18n сам управляет URL, но мы запоминаем выбор для главной страницы.
 */
export function writeStoredDocLocale(locale: DocLocale): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(DOC_LOCALE_STORAGE_KEY, locale);
}

/**
 * Читает предпочтительный язык из localStorage.
 */
export function readStoredDocLocale(): DocLocale | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const raw = window.localStorage.getItem(DOC_LOCALE_STORAGE_KEY);
  if (raw === 'ru' || raw === 'en') {
    return raw;
  }
  return null;
}

/**
 * UI-строки для каждого языка.
 */
export const DOC_UI_STRINGS: Record<DocLocale, TranslationsOption> = {
  ru: {
    search: 'Поиск',
    searchNoResult: 'Ничего не найдено',
    toc: 'На этой странице',
    tocNoHeadings: 'Нет заголовков',
    lastUpdate: 'Обновлено',
    chooseLanguage: 'Язык',
    nextPage: 'Следующая страница',
    previousPage: 'Предыдущая страница',
    chooseTheme: 'Тема',
    editOnGithub: 'Редактировать на GitHub',
  },
  en: {
    search: 'Search',
    searchNoResult: 'No results found',
    toc: 'On this page',
    tocNoHeadings: 'No Headings',
    lastUpdate: 'Last updated on',
    chooseLanguage: 'Language',
    nextPage: 'Next Page',
    previousPage: 'Previous Page',
    chooseTheme: 'Theme',
    editOnGithub: 'Edit on GitHub',
  },
};
