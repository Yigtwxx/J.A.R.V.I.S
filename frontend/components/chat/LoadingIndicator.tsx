'use client';

import { motion } from 'framer-motion';
import dynamic from 'next/dynamic';
import { useChatStore } from '@/store/chatStore';

const LoadingAnimation = dynamic(() => import('../LoadingAnimation'), { ssr: false });

const LoadingIndicator = () => {
    const isLoading = useChatStore(state => state.isLoading);
    const streamingContent = useChatStore(state => state.streamingContent);

    if (!isLoading || !!streamingContent) return null;

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex justify-start w-full max-w-3xl"
        >
            <div className="glass-strong rounded-2xl p-8 w-full flex justify-center border-t-2 border-t-cyan-400 shadow-[0_0_30px_rgba(0,255,255,0.1)]">
                <LoadingAnimation />
            </div>
        </motion.div>
    );
};

export default LoadingIndicator;
