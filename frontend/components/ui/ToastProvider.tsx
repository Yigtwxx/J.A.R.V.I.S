'use client';

import { Toaster } from 'sonner';

export default function ToastProvider() {
    return (
        <Toaster
            theme="dark"
            position="bottom-right"
            richColors
            toastOptions={{
                style: {
                    background: 'rgba(10, 14, 23, 0.95)',
                    border: '1px solid rgba(0, 255, 255, 0.2)',
                    color: '#e2e8f0',
                    backdropFilter: 'blur(16px)',
                },
            }}
        />
    );
}
