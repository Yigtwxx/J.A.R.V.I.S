import '@testing-library/jest-dom';

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
