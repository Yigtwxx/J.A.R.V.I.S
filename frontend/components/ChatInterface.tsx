'use client';

import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Loader2, Cpu, TerminalSquare, Save, CheckCircle } from 'lucide-react';
import { searchPerson, saveProfile } from '@/services/api';
import { Message, SearchResponse } from '@/types/profile';
import ProfileCard from './ProfileCard';
import LoadingAnimation from './LoadingAnimation';
import ReactMarkdown from 'react-markdown';

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: 'SYSTEM ONLINE.\nJ.A.R.V.I.S interface active. Awaiting input for profile analysis sequence.'
        }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSearch = async () => {
        if (!input.trim() || isLoading) return;

        const userMessage: Message = {
            role: 'user',
            content: input.trim()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        try {
            const response = await searchPerson(input.trim());

            const assistantMessage: Message = {
                role: 'assistant',
                content: response.ai_response,
                profileData: response
            };

            setMessages(prev => [...prev, assistantMessage]);

        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage: Message = {
                role: 'assistant',
                content: `[ERROR] Analysis failed: ${axiosError.response?.data?.detail || axiosError.message || 'Unknown error'}. Please verify connection.`
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleApprove = async (messageIndex: number, profileToSave: SearchResponse) => {
        try {
            await saveProfile({
                name: profileToSave.name,
                github_url: profileToSave.github_url,
                instagram_url: profileToSave.instagram_url,
                twitter_url: profileToSave.twitter_url,
                linkedin_url: profileToSave.linkedin_url,
                description: profileToSave.description,
                additional_info: profileToSave.additional_info,
                similar_profiles: profileToSave.similar_profiles
            });

            setMessages(prev => {
                const newMessages = [...prev];
                if (newMessages[messageIndex]) {
                    newMessages[messageIndex] = {
                        ...newMessages[messageIndex],
                        isSaved: true
                    };
                }
                return newMessages;
            });

        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage: Message = {
                role: 'assistant',
                content: `[ERROR] Archive failure: ${axiosError.response?.data?.detail || axiosError.message}`
            };
            setMessages(prev => [...prev, errorMessage]);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSearch();
        }
    };

    return (
        <div className="flex flex-col h-screen relative z-10 grid-background">
            {/* Background elements */}
            <div className="data-stream" />
            <div className="scan-line" />

            {/* Seamless HUD Header */}
            <motion.header
                initial={{ y: -100 }}
                animate={{ y: 0 }}
                transition={{ duration: 0.8, ease: "easeOut" }}
                className="w-full pt-8 pb-4 px-6 fixed top-0 left-0 z-50 pointer-events-none flex justify-center"
            >
                <div className="glass-strong px-10 py-4 rounded-full flex items-center gap-5 border-cyan-400/50 shadow-[0_0_30px_rgba(0,255,255,0.15)]">
                    <Cpu className="w-8 h-8 text-cyan-400 animate-pulse-glow" />
                    <div className="flex flex-col">
                        <h1 className="text-3xl font-orbitron font-black text-gradient tracking-[0.2em] leading-none drop-shadow-lg">
                            J.A.R.V.I.S
                        </h1>
                        <div className="flex items-center gap-2 mt-1">
                            <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />
                            <p className="text-cyan-400 text-xs font-bold uppercase tracking-[0.3em] glow-cyan">
                                System Node Active
                            </p>
                        </div>
                    </div>
                </div>
            </motion.header>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto pt-36 pb-36 px-4 scroll-smooth">
                <div className="max-w-4xl mx-auto space-y-8">
                    <AnimatePresence initial={false}>
                        {messages.map((message, index) => (
                            <motion.div
                                key={index}
                                initial={{ opacity: 0, y: 20, scale: 0.98 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                transition={{ duration: 0.4, ease: "easeOut" }}
                                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                {message.role === 'user' ? (
                                    <div className="message-bubble message-user max-w-xl text-white font-medium shadow-[0_4px_15px_rgba(0,0,0,0.5)] border-white/20">
                                        {message.content}
                                    </div>
                                ) : (
                                    <div className="w-full max-w-3xl space-y-6">
                                        <div className="message-bubble message-ai text-white font-mono text-[15px] leading-normal tracking-wide shadow-lg border-l-4 border-cyan-400">
                                            <div className="flex items-center gap-2 mb-3 text-cyan-400 font-bold pb-2 border-b border-cyan-500/30">
                                                <TerminalSquare className="w-5 h-5 glow-cyan" />
                                                <span className="text-sm uppercase tracking-[0.2em] glow-cyan">System Response</span>
                                            </div>
                                            <ReactMarkdown
                                                components={{
                                                    strong: ({ node, children, ...props }) => {
                                                        // Simple static hash to ensure the same header gets the same color consistently
                                                        const getHash = (str: string) => {
                                                            let hash = 0;
                                                            for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
                                                            return Math.abs(hash);
                                                        };

                                                        const textContent = Array.isArray(children) ? children.join('') : String(children);
                                                        const colors = [
                                                            'text-red-400 drop-shadow-[0_0_8px_rgba(248,113,113,0.8)]',
                                                            'text-green-400 drop-shadow-[0_0_8px_rgba(74,222,128,0.8)]',
                                                            'text-yellow-400 drop-shadow-[0_0_8px_rgba(250,204,21,0.8)]',
                                                            'text-blue-400 drop-shadow-[0_0_8px_rgba(96,165,250,0.8)]',
                                                            'text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.8)]'
                                                        ];
                                                        const colorClass = colors[getHash(textContent) % colors.length];

                                                        return (
                                                            <strong className={`${colorClass} font-black tracking-wider uppercase`} {...props}>
                                                                {children}
                                                            </strong>
                                                        );
                                                    },
                                                    p: ({ node, ...props }) => <p className="leading-normal text-gray-200 mb-2 last:mb-0" {...props} />,
                                                    ul: ({ node, ...props }) => <ul className="list-none space-y-1 mb-2" {...props} />,
                                                    li: ({ node, ...props }) => (
                                                        <li className="flex gap-2">
                                                            <span className="text-cyan-500 mt-0.5">▹</span>
                                                            <span className="text-gray-300" {...props} />
                                                        </li>
                                                    ),
                                                    img: ({ node, ...props }) => (
                                                        <span className="block my-4 rounded-xl overflow-hidden border-2 border-cyan-500/30 w-fit max-w-sm shadow-[0_0_15px_rgba(0,255,255,0.2)]">
                                                            <img className="w-full h-auto object-cover" {...props} alt={props.alt || "Profile Image"} />
                                                        </span>
                                                    ),
                                                    a: ({ node, ...props }) => <a className="text-blue-400 hover:text-cyan-300 underline underline-offset-4 transition-colors" target="_blank" rel="noopener noreferrer" {...props} />
                                                }}
                                            >
                                                {message.content}
                                            </ReactMarkdown>
                                        </div>
                                        {message.profileData && (
                                            <div className="mt-4">
                                                <ProfileCard profile={message.profileData} />
                                                <div className="mt-3 flex flex-col md:flex-row items-end justify-between gap-3 text-right">
                                                    <span className="text-gray-400 italic text-xs max-w-sm">
                                                        Aradığınız sonuç doğruysa daha sonrası için veritabanına kaydetmeniz erişim açısından daha iyi olur.
                                                    </span>
                                                    {!message.isSaved ? (
                                                        <button
                                                            onClick={() => handleApprove(index, message.profileData!)}
                                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-900/40 hover:border-cyan-400 transition-colors shadow-[0_0_10px_rgba(0,255,255,0.1)] shrink-0"
                                                        >
                                                            <Save className="w-4 h-4" />
                                                            <span className="text-sm font-semibold tracking-wide">Kaydet</span>
                                                        </button>
                                                    ) : (
                                                        <div className="flex items-center gap-1.5 px-3 py-1.5 text-green-400 font-medium shrink-0">
                                                            <CheckCircle className="w-5 h-5" />
                                                            <span className="text-sm">DB'ye Kaydedildi</span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </motion.div>
                        ))}
                    </AnimatePresence>

                    {isLoading && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="flex justify-start w-full max-w-3xl"
                        >
                            <div className="glass-strong rounded-2xl p-8 w-full flex justify-center border-t-2 border-t-cyan-400 shadow-[0_0_30px_rgba(0,255,255,0.1)]">
                                <LoadingAnimation />
                            </div>
                        </motion.div>
                    )}

                    <div ref={messagesEndRef} className="h-4" />
                </div>
            </div>

            {/* Futuristic Floating Input Bar */}
            <motion.div
                initial={{ y: 100 }}
                animate={{ y: 0 }}
                transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
                className="fixed bottom-10 left-0 w-full px-6 flex justify-center z-50 pointer-events-none"
            >
                <div className="pointer-events-auto w-full max-w-3xl glass-strong p-2 rounded-2xl flex gap-3 items-center border-2 border-cyan-500/30 shadow-[0_10px_40px_rgba(0,0,0,0.8)] relative overflow-hidden group hover:border-cyan-400/60 transition-colors">
                    <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/10 to-cyan-500/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyPress}
                        placeholder="ENTER TARGET DESIGNATION..."
                        disabled={isLoading}
                        className="flex-1 input-jarvis rounded-xl border-none shadow-none bg-transparent focus:bg-transparent placeholder:tracking-widest text-lg font-bold"
                    />
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

        </div>
    );
}
