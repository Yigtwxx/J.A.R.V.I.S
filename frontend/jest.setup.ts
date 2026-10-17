import '@testing-library/jest-dom';

// next-intl is ESM-only and requires an <NextIntlClientProvider> at render time.
// Mock it globally so any component that calls useTranslations renders in tests
// (the translator is a passthrough that returns the key).
jest.mock('next-intl', () => ({
    useTranslations: () => {
        // Callable plus `.has`, matching the real hook closely enough that a
        // component probing for an optional key does not blow up in tests.
        const t = (key: string) => key;
        t.has = () => false;
        return t;
    },
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

// jsdom does not provide TextEncoder/TextDecoder, which the SSE readers in
// services/api.ts and services/discoveryApi.ts need to decode stream chunks.
// Node's own implementations are spec-compatible, so reuse them.
import { TextDecoder as NodeTextDecoder, TextEncoder as NodeTextEncoder } from 'util';

if (typeof globalThis.TextEncoder === 'undefined') {
    Object.defineProperty(globalThis, 'TextEncoder', { value: NodeTextEncoder });
}
if (typeof globalThis.TextDecoder === 'undefined') {
    Object.defineProperty(globalThis, 'TextDecoder', { value: NodeTextDecoder });
}

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

// jsdom does not implement PointerEvent, so Testing Library's `fireEvent.pointer*`
// silently falls back to a plain Event — which drops `button`, `clientX` and
// `clientY`. A drag fired that way looks to the component like a gesture that
// never moved, so a broken drag handler and a working one are indistinguishable.
// PointerEvent only adds pointer identity on top of MouseEvent, which is exactly
// what the geometry handlers read.
// Guarded on MouseEvent as well: suites that opt into the `node` environment
// (the route handler tests) have no DOM globals at all.
if (typeof globalThis.PointerEvent === 'undefined' && typeof MouseEvent !== 'undefined') {
    class PointerEventPolyfill extends MouseEvent {
        readonly pointerId: number;
        readonly pointerType: string;
        readonly isPrimary: boolean;

        constructor(type: string, params: PointerEventInit = {}) {
            super(type, params);
            this.pointerId = params.pointerId ?? 0;
            this.pointerType = params.pointerType ?? 'mouse';
            this.isPrimary = params.isPrimary ?? true;
        }
    }
    Object.defineProperty(globalThis, 'PointerEvent', { value: PointerEventPolyfill, writable: true });
}

// The capture API rides along with PointerEvent and is likewise absent. The
// component treats capture as best-effort, but leaving these undefined would
// mean the tests never exercise the path a browser actually takes.
if (typeof Element !== 'undefined' && typeof Element.prototype.setPointerCapture === 'undefined') {
    Element.prototype.setPointerCapture = function setPointerCapture() {};
    Element.prototype.releasePointerCapture = function releasePointerCapture() {};
    Element.prototype.hasPointerCapture = function hasPointerCapture() {
        return false;
    };
}
