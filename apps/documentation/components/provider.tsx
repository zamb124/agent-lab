'use client';

import SearchDialog from '@/components/search';
import { DOC_LOCALES, DOC_UI_STRINGS, type DocLocale, readStoredDocLocale, writeStoredDocLocale } from '@/lib/doc-locale';
import { RootProvider } from 'fumadocs-ui/provider/next';
import { useI18n } from 'fumadocs-ui/contexts/i18n';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect } from 'react';
import type { ReactNode } from 'react';

/**
 * Обёртка над RootProvider для управления i18n.
 * Fumadocs i18n сам управляет навигацией через onChange из контекста.
 * Мы только сохраняем выбор в localStorage и обновляем lang атрибут.
 */
export function Provider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { locale: currentLocale, onChange } = useI18n();

  // Обработчик переключения языка — Fumadocs предоставляет onChange
  const onLocaleChange = useCallback(
    (value: string) => {
      if (value !== 'ru' && value !== 'en') {
        throw new Error(`Неподдерживаемый язык документации: ${value}`);
      }
      writeStoredDocLocale(value as DocLocale);
      // Fumadocs onChange сам строит правильный URL
      onChange?.(value);
    },
    [onChange],
  );

  useEffect(() => {
    if (currentLocale) {
      document.documentElement.lang = currentLocale === 'en' ? 'en' : 'ru';
    }
  }, [currentLocale]);

  // При первой загрузке читаем предпочтения из localStorage
  useEffect(() => {
    const stored = readStoredDocLocale();
    if (stored && currentLocale !== stored && onChange) {
      // Если пользователь ранее выбрал другой язык, перенаправляем
      onChange(stored);
    }
  }, [currentLocale, onChange]);

  return (
    <RootProvider
      search={{ SearchDialog }}
      theme={{
        storageKey: 'humanitec-documentation-theme',
        defaultTheme: 'system',
        enableSystem: true,
      }}
      i18n={{
        locale: currentLocale || 'ru',
        locales: DOC_LOCALES,
        onLocaleChange,
        translations: currentLocale && currentLocale in DOC_UI_STRINGS
          ? DOC_UI_STRINGS[currentLocale as DocLocale]
          : DOC_UI_STRINGS.ru,
      }}
    >
      {children}
    </RootProvider>
  );
}
