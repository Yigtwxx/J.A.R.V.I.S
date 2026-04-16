'use client';

import React, { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Send, Loader2, Bot, Search } from 'lucide-react';
import { searchPerson, getSearchHistory } from '@/services/api';
import { Message } from '@/types/profile';
import { useChatStore } from '@/store/chatStore';
import VisionUpload from '@/components/chat/VisionUpload';
import DepthSelector from '@/components/chat/DepthSelector';
import { strings } from '@/lib/strings';

const s = strings.chatInput;

const ChatInputBar = () => {
    const input = useChatStore(state => state.input);
    const setInput = useChatStore(state => state.setInput);
    const isLoading = useChatStore(state => state.isLoading);
    const setIsLoading = useChatStore(state => state.setIsLoading);
    const setMessages = useChatStore(state => state.setMessages);
    const setRagMessages = useChatStore(state => state.setRagMessages);
    const setRagInput = useChatStore(state => state.setRagInput);
    const setStreamingContent = useChatStore(state => state.setStreamingContent);
    const setHistory = useChatStore(state => state.setHistory);
    const isAgentMode = useChatStore(state => state.isAgentMode);
    const setAgentMode = useChatStore(state => state.setAgentMode);
    const searchDepth = useChatStore(state => state.searchDepth);
    const abortControllerRef = useRef<AbortController | null>(null);

    useEffect(() => {
        return () => { abortControllerRef.current?.abort(); };
    }, []);

    const handleSearch = async () => {
        if (!input.trim() || isLoading) return;

        // Cancel any in-flight search
        abortControllerRef.current?.abort();
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const userMessage: Message = {
            id: crypto.randomUUID(),
            role: 'user',
            content: input.trim()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);
        setRagMessages([]);
        setRagInput('');

        try {
            const response = await searchPerson(input.trim(), searchDepth, controller.signal);

            const assistantMessage: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: response.ai_response,
                profileData: response
            };

            setMessages(prev => [...prev, assistantMessage]);
            setStreamingContent('');

            // Background update history
            getSearchHistory().then(setHistory).catch(console.error);

        } catch (error: any) {
            // Ignore intentionally cancelled requests
            if (error.name === 'CanceledError' || error.name === 'AbortError') return;

            setStreamingContent('');
            const detail = error.response?.data?.detail || '';
            const message = error.message || '';
            let errorText: string;

            if (error.response?.status === 504 || detail.toLowerCase().includes('timed out')) {
                errorText = 'The search took too long to complete. Try reducing the search depth or searching a less common name.';
            } else if (message.includes('timeout') || message.includes('Timeout')) {
                errorText = 'Connection timed out while waiting for results. The AI model may be under heavy load. Please try again.';
            } else if (message.includes('Network Error') || message.includes('ECONNREFUSED')) {
                errorText = 'Cannot reach the analysis server. Please verify that the backend and Ollama are running.';
            } else {
                errorText = detail || message || 'An unexpected error occurred. Please try again.';
            }

            const errorMessage: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: `[ERROR] ${errorText}`
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSearch();
        }
    };

    const handleVisionResult = (result: string) => {
        const msg: Message = { id: crypto.randomUUID(), role: 'assistant', content: result };
        setMessages(prev => [...prev, msg]);
    };

    return (
        <motion.div
            initial={{ y: 100 }}
            animate={{ y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
            className="fixed bottom-10 left-0 w-full pl-[300px] pr-[280px] flex justify-center z-50 pointer-events-none"
        >
            <div className="pointer-events-auto w-full max-w-4xl glass-strong p-4 rounded-3xl flex gap-3 items-center border-2 border-cyan-500/30 shadow-[0_10px_40px_rgba(0,0,0,0.8)] relative overflow-visible group hover:border-cyan-400/60 transition-all duration-500">
                <div className="absolute inset-0 overflow-hidden rounded-3xl pointer-events-none">
                    <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/10 to-cyan-500/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />
                </div>

                {/* Agent Mode Toggle */}
                <button
                    onClick={() => setAgentMode(!isAgentMode)}
                    title={isAgentMode ? s.switchToSearch : s.switchToAgent}
                    className={`relative z-10 rounded-xl w-11 h-11 p-0 flex items-center justify-center shrink-0 border-2 transition-all duration-300 ${
                        isAgentMode
                            ? 'border-purple-500/60 bg-purple-900/40 text-purple-300 shadow-[0_0_12px_rgba(168,85,247,0.3)]'
                            : 'border-cyan-500/20 bg-black/20 text-cyan-500/40 hover:text-cyan-300 hover:border-cyan-500/40'
                    }`}
                >
                    {isAgentMode ? <Bot className="w-5 h-5" /> : <Search className="w-5 h-5" />}
                </button>

                {/* Vision Upload */}
                <div className="relative z-10">
                    <VisionUpload onResult={handleVisionResult} />
                </div>

                {/* Depth Selector - Search Mode only */}
                {!isAgentMode && (
                    <div className="relative z-10">
                        <DepthSelector />
                    </div>
                )}

                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder={isAgentMode ? s.placeholderAgent : s.placeholderSearch}
                    disabled={isLoading}
                    className={`flex-1 input-jarvis h-14 rounded-2xl border-none shadow-none bg-black/20 focus:bg-black/40 placeholder:tracking-widest text-xl font-bold px-8 transition-all ${isAgentMode ? 'placeholder:text-purple-500/30' : ''}`}
                />

                <button
                    onClick={handleSearch}
                    disabled={isLoading || !input.trim()}
                    className={`relative z-10 btn-jarvis rounded-xl w-14 h-14 p-0 flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed group/btn border-2 transition-all ${
                        isAgentMode
                            ? 'hover:border-purple-300 bg-purple-950/40 border-purple-500/50'
                            : 'hover:border-cyan-300 bg-cyan-950/40 border-cyan-500/50'
                    }`}
                >
                    {isLoading ? (
                        <Loader2 className={`w-6 h-6 animate-spin ${isAgentMode ? 'text-purple-300' : 'text-cyan-300'}`} />
                    ) : (
                        <Send className={`w-6 h-6 group-hover/btn:text-white group-hover/btn:scale-110 transition-all ${isAgentMode ? 'text-purple-400 drop-shadow-[0_0_8px_rgba(168,85,247,0.8)]' : 'text-cyan-400 drop-shadow-[0_0_8px_rgba(0,255,255,0.8)]'}`} />
                    )}
                </button>
            </div>
        </motion.div>
    );
};

export default ChatInputBar;
