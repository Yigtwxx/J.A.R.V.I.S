import '@testing-library/jest-dom';

// next-intl is ESM-only and requires an <NextIntlClientProvider> at render time.
// Mock it globally so any component that calls useTranslations renders in tests
// (the translator is a passthrough that returns the key).
jest.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useFormatter: () => ({
    dateTime: (value: unknown) => String(value),
    number: (value: unknown) => String(value),
    relativeTime: (value: unknown) => String(value),
  }),
  useLocale: () => 'en',
  useMessages: () => ({}),
  useNow: () => new Date(0),
  useTimeZone: () => 'UTC',
  NextIntlClientProvider: ({ children }: { children: unknown }) => children,
}));

// jsdom does not provide crypto.randomUUID
if (typeof globalThis.crypto === 'undefined') {
  Object.defineProperty(globalThis, 'crypto', {
    value: { randomUUID: () => 'test-uuid-0000' },
  });
} else if (!globalThis.crypto.randomUUID) {
  Object.defineProperty(globalThis.crypto, 'randomUUID', {
    value: () => 'test-uuid-0000',
  });
}
