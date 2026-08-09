'use client';

import React, { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { TerminalSquare, Save, CheckCircle, Search, AlertTriangle, Link2 } from 'lucide-react';
import { toast } from 'sonner';
import { saveProfile, streamStatus } from '@/services/api';
import { Message, SearchResponse } from '@/types/profile';
import ReactMarkdown from 'react-markdown';
import dynamic from 'next/dynamic';
import { useChatStore } from '@/store/chatStore';

// Lazy-loaded Heavy Components
const ProfileCard = dynamic(() => import('./ProfileCard'), { ssr: false });
const VersionHistory = dynamic(() => import('./VersionHistory'), { ssr: false });
const FaceMatch = dynamic(() => import('./FaceMatch'), { ssr: false });

// Extracted Sub-Components — Command Center app shell
import NavRail from '@/components/chat/NavRail';
import IntelDock from '@/components/chat/IntelDock';
import WelcomeScreen from '@/components/chat/WelcomeScreen';
import StreamingMessageBubble from '@/components/chat/StreamingMessageBubble';
import RagInteractionPanel from '@/components/chat/RagInteractionPanel';
import ChatInputBar from '@/components/chat/ChatInputBar';
import LoadingIndicator from '@/components/chat/LoadingIndicator';
import OnboardingHints from '@/components/ui/OnboardingHints';

// Pure utility function — moved to module level
const getHash = (str: string) => {
    let hash = 0;
    for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
    return Math.abs(hash);
};

export default function ChatInterface() {
    const messages = useChatStore((state) => state.messages);
    const setMessages = useChatStore((state) => state.setMessages);
    const setInput = useChatStore((state) => state.setInput);
    const isLoading = useChatStore((state) => state.isLoading);

    const addLiveStatus = useChatStore((state) => state.addLiveStatus);
    const setStreamingContent = useChatStore((state) => state.setStreamingContent);
    const addStreamingToken = useChatStore((state) => state.addStreamingToken);
    const resetSearchState = useChatStore((state) => state.resetSearchState);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let active = true;
        const controller = new AbortController();

        if (isLoading) {
            resetSearchState(); // Reset RAG and Live status

            const handleMessage = (data: string) => {
                if (!active) return; // Guard against stale updates

                if (data === '[STREAM_START]') {
                    // AI streaming is about to begin — clear any previous content
                    setStreamingContent('');
                    return;
                }

                if (data === '[STREAM_END]') {
                    // AI streaming finished — no action needed, final response will replace
                    return;
                }

                if (data.startsWith('[STREAM] ')) {
                    addStreamingToken(data.substring(9));
                } else {
                    addLiveStatus(data);
                }
            };

            // Fetch-based SSE so the API key travels in the X-API-Key header.
            streamStatus(handleMessage, controller.signal).catch((err) => {
                if (err instanceof DOMException && err.name === 'AbortError') return;
                // Stream ended or failed: live status simply stops updating; the
                // search itself completes via its own request.
                console.error('Status stream error:', err);
            });
        } else {
            setStreamingContent('');
        }

        return () => {
            active = false;
            controller.abort();
        };
    }, [isLoading, resetSearchState, addStreamingToken, addLiveStatus, setStreamingContent]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleApprove = async (messageIndex: number, profileToSave: SearchResponse) => {
        try {
            await saveProfile({
                name: profileToSave.name,
                github_url: profileToSave.github_url,
                instagram_url: profileToSave.instagram_url,
                twitter_url: profileToSave.twitter_url,
                linkedin_url: profileToSave.linkedin_url,
                spotify_url: profileToSave.spotify_url,
                tiktok_url: profileToSave.tiktok_url,
                snapchat_url: profileToSave.snapchat_url,
                tumblr_url: profileToSave.tumblr_url,
                youtube_url: profileToSave.youtube_url,
                reddit_url: profileToSave.reddit_url,
                facebook_url: profileToSave.facebook_url,
                pinterest_url: profileToSave.pinterest_url,
                medium_url: profileToSave.medium_url,
                threads_url: profileToSave.threads_url,
                steam_url: profileToSave.steam_url,
                discord_mention: profileToSave.discord_mention,
                tinder_mention: profileToSave.tinder_mention,
                bumble_mention: profileToSave.bumble_mention,
                phone_numbers: profileToSave.phone_numbers,
                description: profileToSave.description,
                additional_info: profileToSave.additional_info,
                similar_profiles: profileToSave.similar_profiles,
                cross_validation_issues: profileToSave.cross_validation_issues,
                network_connections: profileToSave.network_connections,
                email_addresses: profileToSave.email_addresses,
                data_breaches: profileToSave.data_breaches,
            });

            setMessages((prev) => {
                const newMessages = [...prev];
                if (newMessages[messageIndex]) {
                    newMessages[messageIndex] = {
                        ...newMessages[messageIndex],
                        isSaved: true,
                    };
                }
                return newMessages;
            });
        } catch (error: any) {
            const errorMessage: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: `[ERROR] Archive failure: ${error.response?.data?.detail || error.message}`,
            };
            setMessages((prev) => [...prev, errorMessage]);
        }
    };

    return (
        <div className="jarvis-shell grid-background">
            {/* Background element */}
            <div className="data-stream" />

            {/* ── Column 1: Navigation Rail + panel drawer ──────────────── */}
            <NavRail />

            {/* ── Column 2: Workspace ───────────────────────────────────── */}
            <div className="flex flex-col h-screen min-w-0 relative">
                {/* Slim HUD top bar */}
                <header className="shrink-0 flex items-center justify-between px-6 pt-5 pb-3 z-20">
                    <div className="flex items-center gap-2.5">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500 shadow-[0_0_8px_rgba(0,255,255,0.8)]"></span>
                        </span>
                        <span className="text-[10px] font-bold uppercase tracking-[0.35em] text-cyan-300/80 font-mono glow-cyan">
                            System Online
                        </span>
                    </div>
                    <span className="hidden md:inline text-[9px] font-mono tracking-[0.3em] text-cyan-500/40 uppercase">
                        Just A Rather Very Intelligent System
                    </span>
                </header>

                {/* Scrollable content: welcome screen (empty) or message stream */}
                <div className="flex-1 overflow-y-auto px-4 scroll-smooth custom-scrollbar">
                    {messages.length === 0 ? (
                        <WelcomeScreen />
                    ) : (
                        <div className="max-w-4xl mx-auto py-6 space-y-8">
                            <AnimatePresence initial={false}>
                                {messages.map((message, index) => (
                                    <motion.div
                                        key={message.id}
                                        initial={{ opacity: 0, y: 20, scale: 0.98 }}
                                        animate={{ opacity: 1, y: 0, scale: 1 }}
                                        transition={{ duration: 0.4, ease: 'easeOut' }}
                                        className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                                    >
                                        {message.role === 'user' ? (
                                            <div className="message-bubble message-user max-w-xl text-white font-medium">
                                                {message.content}
                                            </div>
                                        ) : message.content.startsWith('[ERROR]') ? (
                                            <div className="w-full max-w-3xl">
                                                <div className="message-bubble bg-red-950/30 border border-red-500/20 rounded-2xl p-5 text-red-200 font-mono text-sm shadow-lg border-l-4 border-l-red-500/60">
                                                    <div className="flex items-center gap-2 mb-3 text-red-400 font-bold pb-2 border-b border-red-500/20">
                                                        <AlertTriangle className="w-5 h-5 text-red-400" />
                                                        <span className="text-xs uppercase tracking-[0.2em]">
                                                            Analysis Error
                                                        </span>
                                                    </div>
                                                    <p className="text-red-200/80 leading-relaxed text-[13px]">
                                                        {message.content.replace('[ERROR] ', '')}
                                                    </p>
                                                    {(() => {
                                                        const prevUserMsg = messages
                                                            .slice(0, index)
                                                            .reverse()
                                                            .find((m) => m.role === 'user');
                                                        if (!prevUserMsg || isLoading) return null;
                                                        return (
                                                            <button
                                                                onClick={() => {
                                                                    setInput(prevUserMsg.content);
                                                                    setMessages((prev) =>
                                                                        prev.filter((m) => m.id !== message.id)
                                                                    );
                                                                }}
                                                                className="mt-3 flex items-center gap-2 px-4 py-2 rounded-xl bg-red-950/40 border border-red-500/30 text-red-300 hover:bg-red-900/40 hover:border-red-400 hover:text-red-200 transition-all text-xs font-bold tracking-wider uppercase"
                                                            >
                                                                <Search className="w-3.5 h-3.5" />
                                                                Retry Search
                                                            </button>
                                                        );
                                                    })()}
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="w-full max-w-3xl space-y-6">
                                                <div className="message-bubble message-ai text-white font-mono text-[15px] leading-normal tracking-wide shadow-lg border-l-4 border-cyan-400">
                                                    <div className="flex items-center gap-2 mb-3 text-cyan-400 font-bold pb-2 border-b border-cyan-500/30">
                                                        <TerminalSquare className="w-5 h-5 glow-cyan" />
                                                        <span className="text-sm uppercase tracking-[0.2em] glow-cyan">
                                                            System Response
                                                        </span>
                                                    </div>
                                                    <ReactMarkdown
                                                        components={{
                                                            strong: ({ children, ...props }) => {
                                                                const textContent = Array.isArray(children)
                                                                    ? children.join('')
                                                                    : String(children);
                                                                const colors = [
                                                                    'text-red-400 drop-shadow-[0_0_8px_rgba(248,113,113,0.8)]',
                                                                    'text-green-400 drop-shadow-[0_0_8px_rgba(74,222,128,0.8)]',
                                                                    'text-yellow-400 drop-shadow-[0_0_8px_rgba(250,204,21,0.8)]',
                                                                    'text-blue-400 drop-shadow-[0_0_8px_rgba(96,165,250,0.8)]',
                                                                    'text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.8)]',
                                                                ];
                                                                const colorClass =
                                                                    colors[getHash(textContent) % colors.length];

                                                                return (
                                                                    <strong
                                                                        className={`${colorClass} font-black tracking-wider uppercase`}
                                                                        {...props}
                                                                    >
                                                                        {children}
                                                                    </strong>
                                                                );
                                                            },
                                                            p: ({ children, ...props }) => {
                                                                const isImageContainer = React.Children.toArray(
                                                                    children
                                                                ).some(
                                                                    (child) =>
                                                                        React.isValidElement(child) &&
                                                                        (child as React.ReactElement<any>).props.node
                                                                            ?.tagName === 'img'
                                                                );
                                                                if (isImageContainer) {
                                                                    return (
                                                                        <div className="flex flex-wrap gap-4 mb-5 items-center justify-start">
                                                                            {children}
                                                                        </div>
                                                                    );
                                                                }
                                                                return (
                                                                    <p
                                                                        className="leading-normal text-gray-200 mb-2 last:mb-0"
                                                                        {...props}
                                                                    >
                                                                        {children}
                                                                    </p>
                                                                );
                                                            },
                                                            ul: ({ ...props }) => (
                                                                <ul className="list-none space-y-1 mb-2" {...props} />
                                                            ),
                                                            li: ({ ...props }) => (
                                                                <li className="flex gap-2">
                                                                    <span className="text-cyan-500 mt-0.5">
                                                                        &#9657;
                                                                    </span>
                                                                    <span className="text-gray-300" {...props} />
                                                                </li>
                                                            ),
                                                            img: ({ ...props }) => {
                                                                const src =
                                                                    typeof props.src === 'string' ? props.src : '';
                                                                const isWikiLogo =
                                                                    src.includes('wikipedia') && src.endsWith('.png');
                                                                if (isWikiLogo) return null; // Filter out rogue wikipedia textual logos
                                                                return (
                                                                    <span className="inline-block shrink-0 rounded-2xl overflow-hidden border-2 border-cyan-500/50 w-32 h-32 sm:w-40 sm:h-40 shadow-[0_0_20px_rgba(0,255,255,0.25)] ring-1 ring-cyan-300/20 transition-transform hover:scale-105">
                                                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                                                        <img
                                                                            className="w-full h-full object-cover object-top"
                                                                            {...props}
                                                                            alt={props.alt || 'Profile Image'}
                                                                            onLoad={(e) => {
                                                                                const target =
                                                                                    e.target as HTMLImageElement;
                                                                                // unavatar.io default generic fallback images usually render at 400x400 dimension exactly
                                                                                if (
                                                                                    target.src.includes(
                                                                                        'unavatar.io'
                                                                                    ) &&
                                                                                    target.naturalWidth === 400 &&
                                                                                    target.naturalHeight === 400
                                                                                ) {
                                                                                    const spanWrapper =
                                                                                        target.parentElement;
                                                                                    if (spanWrapper)
                                                                                        spanWrapper.style.display =
                                                                                            'none';
                                                                                    target.style.display = 'none';
                                                                                }
                                                                            }}
                                                                            onError={(e) => {
                                                                                const target =
                                                                                    e.target as HTMLImageElement;
                                                                                const spanWrapper =
                                                                                    target.parentElement;
                                                                                if (spanWrapper) {
                                                                                    spanWrapper.style.display = 'none';
                                                                                }
                                                                                target.style.display = 'none';
                                                                            }}
                                                                        />
                                                                    </span>
                                                                );
                                                            },
                                                            a: ({ ...props }) => (
                                                                <a
                                                                    className="text-blue-400 hover:text-cyan-300 underline underline-offset-4 transition-colors"
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    {...props}
                                                                />
                                                            ),
                                                        }}
                                                    >
                                                        {message.content}
                                                    </ReactMarkdown>
                                                </div>
                                                {message.profileData && (
                                                    <div className="mt-4">
                                                        <ProfileCard profile={message.profileData} />
                                                        {message.profileData.version_history &&
                                                            message.profileData.version_history.snapshot_count >= 2 && (
                                                                <VersionHistory
                                                                    report={message.profileData.version_history}
                                                                />
                                                            )}
                                                        {message.profileData.face_match_results &&
                                                            message.profileData.face_match_results.total_comparisons >
                                                                0 && (
                                                                <FaceMatch
                                                                    report={message.profileData.face_match_results}
                                                                />
                                                            )}
                                                        <div className="mt-3 flex flex-col md:flex-row items-end justify-between gap-3 text-right">
                                                            <span className="text-gray-400 italic text-xs max-w-sm">
                                                                If this profile looks correct, save it to the database
                                                                for quick access later.
                                                            </span>
                                                            <div className="flex items-center gap-2 shrink-0">
                                                                <button
                                                                    onClick={() => {
                                                                        const url = `${window.location.origin}/?q=${encodeURIComponent(message.profileData!.name)}`;
                                                                        navigator.clipboard.writeText(url).then(() => {
                                                                            toast.success('Link copied!');
                                                                        });
                                                                    }}
                                                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-black/30 border border-cyan-500/20 text-cyan-500/60 hover:text-cyan-300 hover:border-cyan-500/40 transition-colors shrink-0"
                                                                    title="Copy shareable link"
                                                                >
                                                                    <Link2 className="w-4 h-4" />
                                                                    <span className="text-sm font-semibold tracking-wide">
                                                                        Copy Link
                                                                    </span>
                                                                </button>
                                                                {!message.isSaved ? (
                                                                    <button
                                                                        onClick={() =>
                                                                            handleApprove(index, message.profileData!)
                                                                        }
                                                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-900/40 hover:border-cyan-400 transition-colors shadow-[0_0_10px_rgba(0,255,255,0.1)] shrink-0"
                                                                    >
                                                                        <Save className="w-4 h-4" />
                                                                        <span className="text-sm font-semibold tracking-wide">
                                                                            Save
                                                                        </span>
                                                                    </button>
                                                                ) : (
                                                                    <div className="flex items-center gap-1.5 px-3 py-1.5 text-green-400 font-medium shrink-0">
                                                                        <CheckCircle className="w-5 h-5" />
                                                                        <span className="text-sm">Saved to DB</span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>

                                                        {/* RAG Interactive Chat Mode (Only for the latest profile) */}
                                                        {index === messages.length - 1 && (
                                                            <RagInteractionPanel
                                                                profileName={message.profileData.name}
                                                            />
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </motion.div>
                                ))}

                                {/* Live Streaming Message Bubble */}
                                <StreamingMessageBubble />
                            </AnimatePresence>

                            <LoadingIndicator />

                            <div id="messages-end" ref={messagesEndRef} className="h-4" />
                        </div>
                    )}
                </div>

                {/* Futuristic Floating Input Bar (within workspace column) */}
                <ChatInputBar />
            </div>

            {/* ── Column 3: Intel Dock ──────────────────────────────────── */}
            <IntelDock />

            {/* First-visit onboarding hints */}
            <OnboardingHints />
        </div>
    );
}
