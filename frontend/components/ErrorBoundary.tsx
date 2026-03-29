'use client';

import React, { Component, ReactNode } from 'react';

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
    state: State = { hasError: false, error: null };

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error('[J.A.R.V.I.S] Component error:', error, info);
    }

    render() {
        if (this.state.hasError) {
            return this.props.fallback ?? (
                <div className="flex items-center justify-center h-screen bg-black text-cyan-400 font-mono">
                    <div className="text-center space-y-4">
                        <p className="text-2xl font-bold tracking-widest">[SYSTEM FAULT]</p>
                        <p className="text-sm opacity-70">{this.state.error?.message ?? 'Unknown error'}</p>
                        <button
                            onClick={() => this.setState({ hasError: false, error: null })}
                            className="px-4 py-2 border border-cyan-500/50 rounded-lg hover:bg-cyan-950/40 transition-colors"
                        >
                            Reinitialize
                        </button>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}
