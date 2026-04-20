import * as Sentry from '@sentry/nextjs';

const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;

Sentry.init({
    dsn: DSN,
    enabled: !!DSN,
    tracesSampleRate: 0.2,
});
