'use client';

import { useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useChatStore } from '@/store/chatStore';

const RagStreamingBubble = () => {
    const streamingRagContent = useChatStore(state => state.streamingRagContent);
    const isRagLoading = useChatStore(state => state.isRagLoading);

    useEffect(() => {
        document.getElementById('messages-end')?.scrollIntoView({ behavior: 'smooth' });
    }, [streamingRagContent]);

    if (!isRagLoading) return null;

    return (
        <div className="flex justify-start">
            <div className="p-3.5 rounded-xl max-w-[90%] md:max-w-[80%] font-mono text-sm bg-teal-950/30 text-teal-50 border-l-4 border-teal-500 shadow-[0_4px_15px_rgba(45,212,191,0.1)]">
                {streamingRagContent ? (
                    <ReactMarkdown components={{ p: ({ children, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props}>{children}</p> }}>
                        {streamingRagContent}
                    </ReactMarkdown>
                ) : (
                    <div className="flex items-center gap-2 text-teal-400/80">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="uppercase tracking-widest text-xs">Querying deep context nodes...</span>
                    </div>
                )}
            </div>
        </div>
    );
};

export default RagStreamingBubble;
