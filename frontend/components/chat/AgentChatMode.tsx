'use client';

import React, { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bot, Send, Loader2, Wrench } from 'lucide-react';
import { agentChatStream } from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import { AgentMessage } from '@/types/profile';
import ReactMarkdown from 'react-markdown';

const AgentChatMode = () => {
    const agentMessages = useChatStore(state => state.agentMessages);
    const setAgentMessages = useChatStore(state => state.setAgentMessages);
    const isAgentLoading = useChatStore(state => state.isAgentLoading);
    const setIsAgentLoading = useChatStore(state => state.setIsAgentLoading);
    const streamingAgentContent = useChatStore(state => state.streamingAgentContent);
    const setStreamingAgentContent = useChatStore(state => state.setStreamingAgentContent);

    const [input, setInput] = React.useState('');
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }, [agentMessages, streamingAgentContent]);

    const handleSend = async () => {
        if (!input.trim() || isAgentLoading) return;

        const userMsg: AgentMessage = { role: 'user', content: input.trim() };
        setAgentMessages(prev => [...prev, userMsg]);
        setInput('');
        setIsAgentLoading(true);
        setStreamingAgentContent('');

        try {
            const response = await agentChatStream(input.trim(), [...agentMessages, userMsg]);

            if (!response.body) throw new Error('No response body');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let full = '';

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    const chunk = decoder.decode(value, { stream: true });
                    full += chunk;
                    setStreamingAgentContent(full);
                }
            } catch (readError) {
                console.error('Agent stream read failed:', readError);
                if (!full) throw readError;
                full += '\n\n[Stream interrupted]';
            }

            setAgentMessages(prev => [...prev, { role: 'assistant', content: full }]);
            setStreamingAgentContent('');
        } catch (error: unknown) {
            const errMsg = error instanceof Error ? error.message : 'Unknown error';
            setAgentMessages(prev => [...prev, { role: 'assistant', content: `[ERROR] Agent failed: ${errMsg}` }]);
            setStreamingAgentContent('');
        } finally {
            setIsAgentLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="p-3 border-b border-purple-500/20 bg-purple-900/20 flex items-center gap-2">
                <Bot className="w-4 h-4 text-purple-400" />
                <span className="text-[11px] font-mono text-purple-300 tracking-wider uppercase">Agent Mode</span>
                <span className="text-[9px] text-purple-500/50 ml-auto font-mono">AI decides tools</span>
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
                {agentMessages.length === 0 && !streamingAgentContent && (
                    <div className="h-full flex flex-col items-center justify-center text-purple-500/30">
                        <Wrench className="w-10 h-10 mb-3" />
                        <p className="text-xs font-mono">Agent will autonomously choose OSINT tools</p>
                        <p className="text-[10px] font-mono mt-1">Try: &ldquo;Investigate John Doe&rdquo;</p>
                    </div>
                )}

                <AnimatePresence>
                    {agentMessages.map((msg, i) => (
                        <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div className={`max-w-[85%] p-3 rounded-xl text-[12px] ${
                                msg.role === 'user'
                                    ? 'bg-purple-900/40 border border-purple-500/30 text-gray-200'
                                    : msg.role === 'tool'
                                    ? 'bg-yellow-900/20 border border-yellow-500/20 text-yellow-200 font-mono text-[10px]'
                                    : 'bg-cyan-900/20 border border-cyan-500/20 text-gray-300'
                            }`}>
                                {msg.role === 'tool' && <span className="text-[9px] text-yellow-400/60 block mb-1">TOOL RESULT</span>}
                                <div className="prose prose-invert prose-xs max-w-none [&>*]:my-1">
                                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>

                {/* Streaming */}
                {streamingAgentContent && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
                        <div className="max-w-[85%] p-3 rounded-xl bg-cyan-900/20 border border-cyan-500/20 text-gray-300 text-[12px]">
                            <div className="prose prose-invert prose-xs max-w-none [&>*]:my-1">
                                <ReactMarkdown>{streamingAgentContent}</ReactMarkdown>
                            </div>
                            <span className="inline-block w-1.5 h-4 bg-cyan-400 animate-pulse ml-0.5" />
                        </div>
                    </motion.div>
                )}
            </div>

            {/* Input */}
            <div className="p-3 border-t border-purple-500/20 bg-black/20">
                <div className="flex gap-2">
                    <input
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSend())}
                        placeholder="Ask the agent anything..."
                        disabled={isAgentLoading}
                        className="flex-1 bg-black/40 border border-purple-500/20 rounded-xl px-4 py-2.5 text-xs text-gray-200 placeholder:text-purple-500/30 focus:outline-none focus:border-purple-400/50 disabled:opacity-50"
                    />
                    <button onClick={handleSend} disabled={isAgentLoading || !input.trim()}
                        className="p-2.5 bg-purple-900/40 hover:bg-purple-800/40 border border-purple-500/30 rounded-xl text-purple-300 transition-colors disabled:opacity-40"
                    >
                        {isAgentLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default AgentChatMode;
