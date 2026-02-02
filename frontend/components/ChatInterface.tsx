'use client';

import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Send, Loader2 } from 'lucide-react';
import { searchPerson, saveProfile } from '@/services/api';
import { Message, SearchResponse } from '@/types/profile';
import ProfileCard from './ProfileCard';
import ApprovalDialog from './ApprovalDialog';
import LoadingAnimation from './LoadingAnimation';

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: 'Good evening. JARVIS at your service. I can help you search for people and gather their online profiles. Just provide a name and I will do the rest.'
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
                content: `I apologize, but I encountered an error: ${axiosError.response?.data?.detail || axiosError.message || 'Unknown error'}. Please ensure the backend server is running.`
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
                content: `Profile saved successfully to the database, sir. The information for ${pendingProfile.name} is securely stored.`
            };
            setMessages(prev => [...prev, successMessage]);

        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage: Message = {
                role: 'assistant',
                content: `Failed to save profile: ${axiosError.response?.data?.detail || axiosError.message}`
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
            content: 'Understood. The profile has been discarded.'
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
        <div className="flex flex-col h-screen relative">
            {/* Header */}
            <div className="glass-strong border-b border-cyan-400/20 p-4">
                <div className="max-w-4xl mx-auto">
                    <h1 className="text-3xl font-orbitron font-bold glow-cyan">
                        J.A.R.V.I.S
                    </h1>
                    <p className="text-cyan-400/60 text-sm">
                        Just A Rather Very Intelligent System
                    </p>
                </div>
            </div>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-4">
                <div className="max-w-4xl mx-auto space-y-4">
                    {messages.map((message, index) => (
                        <motion.div
                            key={index}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.1 }}
                            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div
                                className={`max-w-2xl ${message.role === 'user'
                                    ? 'glass-strong rounded-lg p-4 border border-cyan-400/30'
                                    : 'w-full'
                                    }`}
                            >
                                {message.role === 'user' ? (
                                    <p className="text-gray-200">{message.content}</p>
                                ) : (
                                    <div className="space-y-4">
                                        <div className="glass rounded-lg p-4 border border-cyan-400/20">
                                            <p className="text-gray-200 whitespace-pre-wrap">
                                                {message.content}
                                            </p>
                                        </div>
                                        {message.profileData && (
                                            <ProfileCard profile={message.profileData} />
                                        )}
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    ))}

                    {isLoading && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="flex justify-start"
                        >
                            <div className="glass-strong rounded-lg p-6 border border-cyan-400/30">
                                <LoadingAnimation />
                            </div>
                        </motion.div>
                    )}

                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Input Area */}
            <div className="glass-strong border-t border-cyan-400/20 p-4">
                <div className="max-w-4xl mx-auto flex gap-3">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyPress}
                        placeholder="Enter a person's name to search..."
                        disabled={isLoading}
                        className="flex-1 input-jarvis rounded-lg"
                    />
                    <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={handleSearch}
                        disabled={isLoading || !input.trim()}
                        className="btn-jarvis rounded-lg px-6 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {isLoading ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                            <Send className="w-5 h-5" />
                        )}
                    </motion.button>
                </div>
            </div>

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
