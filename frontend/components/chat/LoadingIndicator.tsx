'use client';

import { motion } from 'framer-motion';
import dynamic from 'next/dynamic';
import { useChatStore } from '@/store/chatStore';

const LoadingAnimation = dynamic(() => import('../LoadingAnimation'), { ssr: false });

const STATUS_PREFIXES = ['[SYS]', '[PROCESS]', '[OK]', '[WARN]', '[NET'];

function extractStageText(liveStatus: string[]): string | undefined {
    for (let i = liveStatus.length - 1; i >= 0; i--) {
        const line = liveStatus[i];
        if (STATUS_PREFIXES.some(p => line.startsWith(p))) {
            return line
                .replace(/^\[.*?\]\s*/, '')
                .replace(/TAR>.*$/, '')
                .trim()
                .substring(0, 60) || undefined;
        }
    }
    return undefined;
}

const LoadingIndicator = () => {
    const isLoading = useChatStore(state => state.isLoading);
    const streamingContent = useChatStore(state => state.streamingContent);
    const liveStatus = useChatStore(state => state.liveStatus);

    if (!isLoading || !!streamingContent) return null;

    const stageText = extractStageText(liveStatus);

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex justify-start w-full max-w-3xl"
        >
            <div className="glass-strong rounded-2xl p-8 w-full flex justify-center border-t-2 border-t-cyan-400 shadow-[0_0_30px_rgba(0,255,255,0.1)]">
                <LoadingAnimation subText={stageText} />
            </div>
        </motion.div>
    );
};

export default LoadingIndicator;
