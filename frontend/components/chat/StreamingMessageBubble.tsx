'use client';

import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { TerminalSquare } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useChatStore } from '@/store/chatStore';

const StreamingMessageBubble = () => {
    const streamingContent = useChatStore(state => state.streamingContent);
    const isLoading = useChatStore(state => state.isLoading);

    useEffect(() => {
        document.getElementById('messages-end')?.scrollIntoView({ behavior: 'smooth' });
    }, [streamingContent]);

    if (!isLoading || !streamingContent) return null;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex justify-start"
        >
            <div className="w-full max-w-3xl space-y-6">
                <div className="message-bubble message-ai text-white font-mono text-[15px] leading-normal tracking-wide shadow-lg border-l-4 border-cyan-400 relative">
                    <div className="flex items-center gap-2 mb-3 text-cyan-400 font-bold pb-2 border-b border-cyan-500/30">
                        <TerminalSquare className="w-5 h-5 glow-cyan animate-pulse" />
                        <span className="text-sm uppercase tracking-[0.2em] glow-cyan">Receiving Transmission...</span>
                    </div>
                    <ReactMarkdown
                        components={{
                            p: ({ children, ...props }) => <p className="leading-normal text-gray-200 mb-2 last:mb-0" {...props}>{children}</p>,
                        }}
                    >
                        {streamingContent}
                    </ReactMarkdown>
                    <span className="inline-block w-2.5 h-4 ml-1 bg-cyan-400 animate-pulse align-middle shadow-[0_0_8px_cyan]" />
                </div>
            </div>
        </motion.div>
    );
};

export default StreamingMessageBubble;
