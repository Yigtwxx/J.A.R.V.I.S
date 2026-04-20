'use client';

import dynamic from 'next/dynamic';
import { Suspense, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useChatStore } from '@/store/chatStore';

const Background = dynamic(() => import('../components/Background'));
const ChatInterface = dynamic(() => import('../components/ChatInterface'));

function SearchInitializer() {
    const searchParams = useSearchParams();
    const setInput = useChatStore(state => state.setInput);

    useEffect(() => {
        const q = searchParams.get('q');
        if (q) {
            setInput(q);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return null;
}

export default function Home() {
    return (
        <main className="min-h-screen relative">
            <Background />
            <Suspense fallback={null}>
                <SearchInitializer />
            </Suspense>
            <ChatInterface />
        </main>
    );
}
