import * as Sentry from '@sentry/nextjs';

// Server runtime should prefer the non-public SENTRY_DSN; fall back to the
// public DSN so a single-variable setup still works.
const DSN = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;

Sentry.init({
    dsn: DSN,
    enabled: !!DSN,
    tracesSampleRate: 0.2,
});
