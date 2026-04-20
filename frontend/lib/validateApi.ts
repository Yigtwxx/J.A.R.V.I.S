import { z } from 'zod';
import * as Sentry from '@sentry/nextjs';

/**
 * Validates `data` against `schema` at runtime. On failure, warns in the
 * console and adds a Sentry breadcrumb. Always returns the raw data so the
 * app keeps working with whatever the server sent (extra fields are preserved).
 */
export function validateResponse<T>(
    schema: z.ZodType<T>,
    data: unknown,
    label: string,
): T {
    const result = schema.safeParse(data);
    if (!result.success) {
        const issues = result.error.flatten();
        console.warn(`[J.A.R.V.I.S] API validation warning (${label}):`, issues);
        Sentry.addBreadcrumb({
            category: 'api.validation',
            message: `Validation failed: ${label}`,
            level: 'warning',
            data: { issues },
        });
    }
    // Always return raw data — preserves extra fields the API may send
    return data as T;
}
