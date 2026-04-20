'use client';

import * as Sentry from '@sentry/nextjs';
import { useEffect } from 'react';

export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        Sentry.captureException(error);
    }, [error]);

    return (
        <html>
            <body className="bg-black text-cyan-400 font-mono">
                <div className="flex items-center justify-center min-h-screen">
                    <div className="text-center space-y-6">
                        <p className="text-2xl font-bold tracking-widest">[CRITICAL SYSTEM FAULT]</p>
                        <p className="text-sm opacity-70 max-w-md mx-auto">
                            {error.message || 'A fatal application error has occurred.'}
                        </p>
                        <button
                            onClick={reset}
                            className="px-6 py-3 border border-cyan-500/50 rounded-lg hover:bg-cyan-950/40 transition-colors text-sm tracking-widest uppercase"
                        >
                            Reinitialize
                        </button>
                    </div>
                </div>
            </body>
        </html>
    );
}
