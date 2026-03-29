'use client';

import React from 'react';
import { TerminalSquare, Send, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useChatStore } from '@/store/chatStore';
import { API_BASE_URL } from '@/services/api';
import RagStreamingBubble from '@/components/chat/RagStreamingBubble';

const RagInteractionPanel = ({ profileName }: { profileName: string }) => {
    const ragInput = useChatStore(state => state.ragInput);
    const setRagInput = useChatStore(state => state.setRagInput);
    const ragMessages = useChatStore(state => state.ragMessages);
    const setRagMessages = useChatStore(state => state.setRagMessages);
    const isRagLoading = useChatStore(state => state.isRagLoading);
    const setIsRagLoading = useChatStore(state => state.setIsRagLoading);
    const setStreamingRagContent = useChatStore(state => state.setStreamingRagContent);

    const handleRagSubmit = async () => {
        if (!ragInput.trim() || isRagLoading) return;

        const userMessage = { role: 'user' as const, content: ragInput.trim() };
        setRagMessages(prev => [...prev, userMessage]);
        setRagInput('');
        setIsRagLoading(true);
        setStreamingRagContent('');

        try {
            const response = await fetch(`${API_BASE_URL}/api/chat/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query_name: profileName,
                    messages: ragMessages.concat(userMessage)
                })
            });

            if (!response.ok) throw new Error('RAG Chat failed');

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let aiContent = '';

            if (reader) {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    aiContent += chunk;
                    setStreamingRagContent(aiContent);
                }
            }

            setRagMessages(prev => [...prev, { role: 'assistant', content: aiContent }]);
            setStreamingRagContent('');

        } catch (error) {
            console.error(error);
            setRagMessages(prev => [...prev, { role: 'assistant', content: '[SYSTEM ERROR: Neural reasoning engine failure. Check API logs.]' }]);
            setStreamingRagContent('');
        } finally {
            setIsRagLoading(false);
        }
    };

    return (
        <div className="mt-8 border-t-2 border-cyan-500/20 pt-5">
            <div className="flex items-center gap-2 mb-4">
                <TerminalSquare className="w-5 h-5 text-teal-400 drop-shadow-[0_0_8px_rgba(45,212,191,0.8)]" />
                <span className="text-sm font-bold font-mono text-teal-300 uppercase tracking-widest drop-shadow-[0_0_5px_rgba(45,212,191,0.5)]">
                    Interactive Analysis Protocol
                </span>
            </div>

            <div className="space-y-4 mb-4">
                {ragMessages.map((ragMsg, rIndex) => (
                    <div key={rIndex} className={`flex ${ragMsg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`p-3.5 rounded-xl max-w-[90%] md:max-w-[80%] font-mono text-sm shadow-md ${ragMsg.role === 'user' ? 'bg-cyan-950/40 text-cyan-50 border border-cyan-500/30' : 'bg-teal-950/30 text-teal-50 border-l-4 border-teal-500 shadow-[0_4px_15px_rgba(45,212,191,0.1)]'}`}>
                            {ragMsg.role === 'assistant' ? (
                                <ReactMarkdown components={{ p: ({ children, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props}>{children}</p> }}>
                                    {ragMsg.content}
                                </ReactMarkdown>
                            ) : ragMsg.content}
                        </div>
                    </div>
                ))}

                <RagStreamingBubble />
            </div>

            <div className="flex gap-2">
                <input
                    type="text"
                    value={ragInput}
                    onChange={(e) => setRagInput(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRagSubmit();
                    }}
                    disabled={isRagLoading}
                    placeholder={`Ask J.A.R.V.I.S about ${profileName}...`}
                    className="flex-1 bg-black/40 border border-cyan-500/30 rounded-xl px-4 py-3 text-cyan-100 font-mono text-sm focus:border-teal-400 focus:outline-none placeholder:text-cyan-500/40 transition-colors shadow-inner"
                />
                <button
                    onClick={handleRagSubmit}
                    disabled={isRagLoading || !ragInput.trim()}
                    className="bg-cyan-950/50 border border-cyan-500/50 hover:border-teal-400 hover:text-teal-300 text-cyan-400 px-5 py-3 rounded-xl font-mono tracking-widest uppercase transition-all flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed group/ragbtn"
                >
                    {isRagLoading ? <Loader2 className="w-5 h-5 animate-spin text-teal-400" /> : <Send className="w-5 h-5 group-hover/ragbtn:scale-110 transition-transform" />}
                </button>
            </div>
        </div>
    );
};

export default RagInteractionPanel;
