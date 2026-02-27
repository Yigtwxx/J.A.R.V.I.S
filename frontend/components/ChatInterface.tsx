'use client';

import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Loader2, Cpu, TerminalSquare } from 'lucide-react';
import { searchPerson, saveProfile } from '@/services/api';
import { Message, SearchResponse } from '@/types/profile';
import ProfileCard from './ProfileCard';
import ApprovalDialog from './ApprovalDialog';
import LoadingAnimation from './LoadingAnimation';

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: 'SYSTEM ONLINE.\nJ.A.R.V.I.S interface active. Awaiting input for profile analysis sequence.'
        }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [pendingProfile, setPendingProfile] = useState<SearchResponse | null>(null);
    const [showApproval, setShowApproval] = useState(false);
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
            setPendingProfile(response);
            setShowApproval(true);

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

    const handleApprove = async () => {
        if (!pendingProfile) return;

        try {
            await saveProfile({
                name: pendingProfile.name,
                github_url: pendingProfile.github_url,
                instagram_url: pendingProfile.instagram_url,
                twitter_url: pendingProfile.twitter_url,
                linkedin_url: pendingProfile.linkedin_url,
                description: pendingProfile.description,
                additional_info: pendingProfile.additional_info,
                similar_profiles: pendingProfile.similar_profiles
            });

            const successMessage: Message = {
                role: 'assistant',
                content: `Profile successfully archived. Target: ${pendingProfile.name}. Data secured.`
            };
            setMessages(prev => [...prev, successMessage]);

        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage: Message = {
                role: 'assistant',
                content: `[ERROR] Archive failure: ${axiosError.response?.data?.detail || axiosError.message}`
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setShowApproval(false);
            setPendingProfile(null);
        }
    };

    const handleReject = () => {
        const rejectMessage: Message = {
            role: 'assistant',
            content: 'Data discarded. Awaiting next command.'
        };
        setMessages(prev => [...prev, rejectMessage]);
        setShowApproval(false);
        setPendingProfile(null);
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
                <div className="glass px-8 py-3 rounded-full flex items-center gap-4">
                    <Cpu className="w-5 h-5 text-cyan-400 animate-pulse-glow" />
                    <div>
                        <h1 className="text-xl font-orbitron font-bold text-gradient tracking-widest leading-none">
                            J.A.R.V.I.S
                        </h1>
                        <p className="text-cyan-400/50 text-[10px] uppercase font-mono tracking-widest mt-1">
                            System Node Active
                        </p>
                    </div>
                </div>
            </motion.header>

            {/* Messages Area - Expanded and Seamless */}
            <div className="flex-1 overflow-y-auto pt-32 pb-32 px-4 scroll-smooth">
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
                                    <div className="message-bubble message-user max-w-xl text-gray-300 font-light">
                                        {message.content}
                                    </div>
                                ) : (
                                    <div className="w-full max-w-3xl space-y-6">
                                        <div className="message-bubble message-ai text-cyan-100/90 whitespace-pre-wrap font-mono text-sm leading-relaxed tracking-wide">
                                            <div className="flex items-center gap-2 mb-2 text-cyan-500/60 pb-2 border-b border-cyan-500/10">
                                                <TerminalSquare className="w-4 h-4" />
                                                <span className="text-xs uppercase tracking-widest">System Response</span>
                                            </div>
                                            {message.content}
                                        </div>
                                        {message.profileData && (
                                            <ProfileCard profile={message.profileData} />
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
                            <div className="glass-strong rounded-2xl p-8 w-full flex justify-center border-t-2 border-t-cyan-500/40">
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
                className="fixed bottom-8 left-0 w-full px-6 flex justify-center z-50 pointer-events-none"
            >
                <div className="pointer-events-auto w-full max-w-3xl glass-strong p-2 rounded-2xl flex gap-2 items-center border border-cyan-500/20 shadow-2xl relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/5 to-cyan-500/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyPress}
                        placeholder="ENTER TARGET DESIGNATION..."
                        disabled={isLoading}
                        className="flex-1 input-jarvis rounded-xl border-none shadow-none bg-transparent focus:bg-transparent placeholder:tracking-widest"
                    />
                    <button
                        onClick={handleSearch}
                        disabled={isLoading || !input.trim()}
                        className="btn-jarvis rounded-xl w-12 h-12 p-0 flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed group/btn hover:border-cyan-400"
                    >
                        {isLoading ? (
                            <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
                        ) : (
                            <Send className="w-5 h-5 text-cyan-500 group-hover/btn:text-cyan-300 transition-colors" />
                        )}
                    </button>
                </div>
            </motion.div>

            {/* Approval Dialog */}
            {pendingProfile && (
                <ApprovalDialog
                    profile={pendingProfile}
                    isOpen={showApproval}
                    onApprove={handleApprove}
                    onReject={handleReject}
                />
            )}
        </div>
    );
}
