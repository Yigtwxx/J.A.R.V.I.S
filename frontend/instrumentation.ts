export async function register() {
    if (process.env.NEXT_RUNTIME === 'nodejs') {
        await import('./sentry.server.config');
    }
    if (process.env.NEXT_RUNTIME === 'edge') {
        await import('./sentry.edge.config');
    }
}

export const onRequestError = (...args: Parameters<typeof import('@sentry/nextjs').captureRequestError>) =>
    import('@sentry/nextjs').then(({ captureRequestError }) => captureRequestError(...args));
