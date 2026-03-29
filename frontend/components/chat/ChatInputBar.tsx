'use client';

import React, { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Send, Loader2, Mic, MicOff, Volume2, VolumeX } from 'lucide-react';
import { searchPerson, getSearchHistory } from '@/services/api';
import { Message } from '@/types/profile';
import { useChatStore } from '@/store/chatStore';

const ChatInputBar = () => {
    const input = useChatStore(state => state.input);
    const setInput = useChatStore(state => state.setInput);
    const isLoading = useChatStore(state => state.isLoading);
    const setIsLoading = useChatStore(state => state.setIsLoading);
    const isListening = useChatStore(state => state.isListening);
    const setIsListening = useChatStore(state => state.setIsListening);
    const voiceEnabled = useChatStore(state => state.voiceEnabled);
    const setVoiceEnabled = useChatStore(state => state.setVoiceEnabled);
    const setMessages = useChatStore(state => state.setMessages);
    const setRagMessages = useChatStore(state => state.setRagMessages);
    const setRagInput = useChatStore(state => state.setRagInput);
    const setStreamingContent = useChatStore(state => state.setStreamingContent);
    const setHistory = useChatStore(state => state.setHistory);

    const recognitionRef = useRef<any>(null);

    useEffect(() => {
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (SpeechRecognition) {
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = false;
            recognitionRef.current.interimResults = false;
            recognitionRef.current.lang = 'en-US';

            recognitionRef.current.onresult = (event: any) => {
                const transcript = event.results[0][0].transcript;
                const currentInput = useChatStore.getState().input;
                setInput(currentInput + (currentInput ? ' ' : '') + transcript);
                setIsListening(false);
            };

            recognitionRef.current.onerror = () => setIsListening(false);
            recognitionRef.current.onend = () => setIsListening(false);
        }
    }, [setInput, setIsListening]);

    const toggleListening = () => {
        if (isListening) {
            recognitionRef.current?.stop();
            setIsListening(false);
        } else {
            recognitionRef.current?.start();
            setIsListening(true);
        }
    };

    const handleSearch = async () => {
        if (!input.trim() || isLoading) return;

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
            const response = await searchPerson(input.trim());

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
            setStreamingContent('');
            const errorMessage: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: `[ERROR] Analysis failed: ${error.response?.data?.detail || error.message || 'Unknown error'}. Please verify connection.`
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

    return (
        <motion.div
            initial={{ y: 100 }}
            animate={{ y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
            className="fixed bottom-10 left-0 w-full pl-[300px] pr-[280px] flex justify-center z-50 pointer-events-none"
        >
            <div className="pointer-events-auto w-full max-w-4xl glass-strong p-4 rounded-3xl flex gap-4 items-center border-2 border-cyan-500/30 shadow-[0_10px_40px_rgba(0,0,0,0.8)] relative overflow-hidden group hover:border-cyan-400/60 transition-all duration-500">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/10 to-cyan-500/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />

                <button
                    onClick={() => {
                        if (voiceEnabled) window.speechSynthesis.cancel();
                        setVoiceEnabled(!voiceEnabled);
                    }}
                    className={`p-3 rounded-xl border transition-all ${voiceEnabled ? 'border-cyan-400 bg-cyan-900/40 text-cyan-400 glow-cyan' : 'border-slate-700 bg-slate-900/40 text-slate-500'}`}
                    title={voiceEnabled ? "Mute JARVIS" : "Enable JARVIS Voice"}
                >
                    {voiceEnabled ? <Volume2 className="w-6 h-6" /> : <VolumeX className="w-6 h-6" />}
                </button>

                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="Enter name or username (use '/' to separate)..."
                    disabled={isLoading}
                    className="flex-1 input-jarvis h-14 rounded-2xl border-none shadow-none bg-black/20 focus:bg-black/40 placeholder:tracking-widest text-xl font-bold px-8 transition-all"
                />

                <button
                    onClick={toggleListening}
                    className={`relative w-14 h-14 rounded-xl flex items-center justify-center transition-all border-2 ${isListening ? 'border-red-500 bg-red-950/40 text-red-500' : 'border-cyan-500/50 bg-cyan-950/40 text-cyan-400 hover:border-cyan-300'}`}
                >
                    {isListening && (
                        <motion.div
                            animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
                            transition={{ repeat: Infinity, duration: 1.5 }}
                            className="absolute inset-0 bg-red-500/30 rounded-full"
                        />
                    )}
                    {isListening ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                </button>

                <button
                    onClick={handleSearch}
                    disabled={isLoading || !input.trim()}
                    className="btn-jarvis rounded-xl w-14 h-14 p-0 flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed group/btn hover:border-cyan-300 bg-cyan-950/40 border-2 border-cyan-500/50"
                >
                    {isLoading ? (
                        <Loader2 className="w-6 h-6 animate-spin text-cyan-300" />
                    ) : (
                        <Send className="w-6 h-6 text-cyan-400 group-hover/btn:text-white group-hover/btn:scale-110 transition-all drop-shadow-[0_0_8px_rgba(0,255,255,0.8)]" />
                    )}
                </button>
            </div>
        </motion.div>
    );
};

export default ChatInputBar;
