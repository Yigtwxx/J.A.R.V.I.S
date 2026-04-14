'use client';

import { useEffect } from 'react';

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error('[J.A.R.V.I.S] Page error:', error);
    }, [error]);

    return (
        <div className="flex items-center justify-center min-h-screen bg-black text-cyan-400 font-mono">
            <div className="text-center space-y-6">
                <p className="text-2xl font-bold tracking-widest">[SYSTEM FAULT]</p>
                <p className="text-sm opacity-70 max-w-md mx-auto">
                    {error.message || 'An unexpected error occurred.'}
                </p>
                <button
                    onClick={reset}
                    className="px-6 py-3 border border-cyan-500/50 rounded-lg hover:bg-cyan-950/40 transition-colors text-sm tracking-widest uppercase"
                >
                    Reinitialize
                </button>
            </div>
        </div>
    );
}
