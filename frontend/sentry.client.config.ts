// Client-side Sentry initialization now lives in `instrumentation-client.ts`
// (the Next.js-native client instrumentation entrypoint). This file is kept as
// a no-op because @sentry/nextjs' webpack plugin still injects an import for it;
// calling Sentry.init() here as well would initialize the SDK twice on the client.
export {};
