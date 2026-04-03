'use client';

import React, { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { TerminalSquare, Save, CheckCircle, Github, Instagram, Twitter, Linkedin, Globe, MapPin, Thermometer, Cloud, Sun, Wind, Search } from 'lucide-react';
import { saveProfile, API_BASE_URL } from '@/services/api';
import { Message, SearchResponse } from '@/types/profile';
import ReactMarkdown from 'react-markdown';
import dynamic from 'next/dynamic';
import { useChatStore } from '@/store/chatStore';
import ScrambleText from '@/components/ui/ScrambleText';
import GlitchText from '@/components/ui/GlitchText';

// Lazy-loaded Heavy Components
const ProfileCard = dynamic(() => import('./ProfileCard'), { ssr: false });
const VersionHistory = dynamic(() => import('./VersionHistory'), { ssr: false });
const FaceMatch = dynamic(() => import('./FaceMatch'), { ssr: false });
const SocialGauge = dynamic(() => import('./SocialGauge'), { ssr: false });
const SentimentGauge = dynamic(() => import('./SentimentGauge'), { ssr: false });

// Custom Brand Icons
import { SpotifyIcon, TikTokIcon, SnapchatIcon, TumblrIcon, TinderIcon,
         BumbleIcon, YoutubeIcon, RedditIcon, FacebookIcon, PhoneIcon,
         PinterestIcon, MediumIcon, ThreadsIcon, SteamIcon, DiscordIcon } from '@/components/ui/Icons';

// Extracted Sub-Components
import LiveStatusMonitor from '@/components/chat/LiveStatusMonitor';
import StreamingMessageBubble from '@/components/chat/StreamingMessageBubble';
import HistorySidebar from '@/components/chat/HistorySidebar';
import RagInteractionPanel from '@/components/chat/RagInteractionPanel';
import ChatInputBar from '@/components/chat/ChatInputBar';
import LoadingIndicator from '@/components/chat/LoadingIndicator';


// Pure utility function — moved to module level
const getHash = (str: string) => {
    let hash = 0;
    for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
    return Math.abs(hash);
};

export default function ChatInterface() {
    const messages = useChatStore(state => state.messages);
    const setMessages = useChatStore(state => state.setMessages);
    const isLoading = useChatStore(state => state.isLoading);

    const addLiveStatus = useChatStore(state => state.addLiveStatus);
    const setStreamingContent = useChatStore(state => state.setStreamingContent);
    const addStreamingToken = useChatStore(state => state.addStreamingToken);
    const resetSearchState = useChatStore(state => state.resetSearchState);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let eventSource: EventSource | null = null;
        let intentionalClose = false;

        if (isLoading) {
            resetSearchState(); // Reset RAG and Live status
            eventSource = new EventSource(`${API_BASE_URL}/api/status/stream`);

            eventSource.onmessage = (event) => {
                const data = event.data as string;

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
                    const token = data.substring(9);
                    addStreamingToken(token);
                } else {
                    addLiveStatus(data);
                }
            };

            eventSource.onerror = () => {
                // Only close if not intentionally closed (prevents infinite reconnect loop)
                if (!intentionalClose && eventSource?.readyState !== EventSource.CLOSED) {
                    eventSource?.close();
                }
            };
        } else {
            setStreamingContent('');
        }

        return () => {
            intentionalClose = true;
            if (eventSource) eventSource.close();
        };
    }, [isLoading, resetSearchState, addStreamingToken, addLiveStatus, setStreamingContent]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const lastProfile = React.useMemo(
        () => [...messages].reverse().find(m => m.role === 'assistant' && m.profileData)?.profileData,
        [messages]
    );

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

        } catch (error: any) {
            const errorMessage: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: `[ERROR] Archive failure: ${error.response?.data?.detail || error.message}`
            };
            setMessages(prev => [...prev, errorMessage]);
        }
    };

    return (
        <div className="flex flex-col h-screen relative z-10 grid-background">
            {/* Background elements */}
            <div className="data-stream" />
            <div className="scan-line" />

            {/* Seamless HUD Header */}
            <motion.header
                initial={{ top: "40%", left: "50%", x: "-50%", y: "-50%", scale: 1.2 }}
                animate={{
                    top: messages.length === 0 ? "40%" : "2rem",
                    left: messages.length === 0 ? "50%" : "1.5rem",
                    x: messages.length === 0 ? "-50%" : "0%",
                    y: messages.length === 0 ? "-50%" : "0%",
                    scale: messages.length === 0 ? 1.2 : 0.85
                }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="fixed z-50 pointer-events-none origin-top-left"
            >
                <div className="flex flex-col items-center gap-4">
                    <div className="flex items-center gap-5">
                        <div className="relative w-12 h-12 rounded-xl overflow-hidden border-2 border-cyan-500/60 shadow-[0_0_20px_rgba(0,255,255,0.3)] bg-black/40 flex items-center justify-center">
                            <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/20 to-transparent" />
                            <span className="text-xl font-black text-cyan-400 font-orbitron glow-cyan select-none">J</span>
                        </div>
                        <h1 className="text-3xl md:text-4xl font-black tracking-[0.3em] uppercase font-orbitron">
                            <GlitchText
                                text="J.A.R.V.I.S"
                                interval={5000}
                                className="text-transparent bg-clip-text bg-gradient-to-r from-white via-cyan-100 to-cyan-400"
                            />
                        </h1>
                        <div className="flex items-center gap-2.5 mt-1">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500 shadow-[0_0_8px_rgba(0,255,255,0.8)]"></span>
                            </span>
                            <p className="text-cyan-300/90 text-[10px] font-bold uppercase tracking-[0.4em] glow-cyan font-mono">
                                Just A Rather Very Intelligent System
                            </p>
                        </div>
                    </div>
                </div>
            </motion.header>

            {/* History Sidebar */}
            <HistorySidebar />

            {/* Right Sidebar: Network Nodes or Live Status */}
            {(() => {
                // If loading, show live status stream
                if (isLoading) {
                    return <LiveStatusMonitor />;
                }

                if (!lastProfile) return null;

                // Search fallback URL generator for platforms without found profiles
                const searchName = lastProfile.name || '';
                const encoded = encodeURIComponent(searchName);
                const searchUrls: Record<string, string> = {
                    'GitHub': `https://github.com/search?q=${encoded}&type=users`,
                    'Instagram': `https://www.google.com/search?q=site:instagram.com+${encoded}`,
                    'X (Twitter)': `https://x.com/search?q=${encoded}&f=user`,
                    'LinkedIn': `https://www.linkedin.com/search/results/people/?keywords=${encoded}`,
                    'Spotify': `https://open.spotify.com/search/${encoded}`,
                    'TikTok': `https://www.tiktok.com/search/user?q=${encoded}`,
                    'Snapchat': `https://www.snapchat.com/add/${encoded}`,
                    'Tumblr': `https://www.tumblr.com/search/${encoded}`,
                    'YouTube': `https://www.youtube.com/results?search_query=${encoded}`,
                    'Reddit': `https://www.reddit.com/search/?q=${encoded}&type=user`,
                    'Facebook': `https://www.facebook.com/search/people/?q=${encoded}`,
                    'Pinterest': `https://www.pinterest.com/search/users/?q=${encoded}`,
                    'Medium': `https://medium.com/search?q=${encoded}`,
                    'Threads': `https://www.threads.net/search?q=${encoded}&serp_type=default`,
                    'Steam': `https://steamcommunity.com/search/users/#text=${encoded}`,
                };

                const allPlatforms = [
                    { icon: Github, urls: lastProfile.github_url, label: 'GitHub', brandStyles: 'border-gray-500/40 bg-gray-900/50 hover:bg-gray-800/80 hover:border-gray-400 text-gray-300 shadow-[0_4px_15px_rgba(156,163,175,0.15)]' },
                    { icon: Instagram, urls: lastProfile.instagram_url, label: 'Instagram', brandStyles: 'border-pink-500/40 bg-fuchsia-950/40 hover:bg-fuchsia-900/60 hover:border-pink-400 text-pink-400 shadow-[0_4px_15px_rgba(236,72,153,0.15)]' },
                    { icon: Twitter, urls: lastProfile.twitter_url, label: 'X (Twitter)', brandStyles: 'border-slate-500/40 bg-slate-900/50 hover:bg-slate-800/80 hover:border-slate-300 text-slate-300 shadow-[0_4px_15px_rgba(148,163,184,0.15)]' },
                    { icon: Linkedin, urls: lastProfile.linkedin_url, label: 'LinkedIn', brandStyles: 'border-blue-500/40 bg-blue-950/50 hover:bg-blue-900/60 hover:border-blue-400 text-blue-400 shadow-[0_4px_15px_rgba(59,130,246,0.15)]' },
                    { icon: SpotifyIcon, urls: lastProfile.spotify_url, label: 'Spotify', brandStyles: 'border-green-500/40 bg-emerald-950/40 hover:bg-emerald-900/60 hover:border-green-400 text-green-400 shadow-[0_4px_15px_rgba(34,197,94,0.15)]' },
                    { icon: TikTokIcon, urls: lastProfile.tiktok_url, label: 'TikTok', brandStyles: 'border-rose-500/40 bg-rose-950/40 hover:bg-rose-900/60 hover:border-rose-400 text-rose-400 shadow-[0_4px_15px_rgba(244,63,94,0.15)]' },
                    { icon: SnapchatIcon, urls: lastProfile.snapchat_url, label: 'Snapchat', brandStyles: 'border-yellow-500/40 bg-yellow-950/40 hover:bg-yellow-900/60 hover:border-yellow-400 text-yellow-400 shadow-[0_4px_15px_rgba(250,204,21,0.15)]' },
                    { icon: TumblrIcon, urls: lastProfile.tumblr_url, label: 'Tumblr', brandStyles: 'border-indigo-500/40 bg-indigo-950/40 hover:bg-indigo-900/60 hover:border-indigo-400 text-indigo-400 shadow-[0_4px_15px_rgba(99,102,241,0.15)]' },
                    { icon: YoutubeIcon, urls: lastProfile.youtube_url, label: 'YouTube', brandStyles: 'border-red-500/40 bg-red-950/40 hover:bg-red-900/60 hover:border-red-400 text-red-400 shadow-[0_4px_15px_rgba(239,68,68,0.15)]' },
                    { icon: RedditIcon, urls: lastProfile.reddit_url, label: 'Reddit', brandStyles: 'border-orange-500/40 bg-orange-950/40 hover:bg-orange-900/60 hover:border-orange-400 text-orange-400 shadow-[0_4px_15px_rgba(249,115,22,0.15)]' },
                    { icon: FacebookIcon, urls: lastProfile.facebook_url, label: 'Facebook', brandStyles: 'border-blue-600/40 bg-blue-950/40 hover:bg-blue-900/60 hover:border-blue-500 text-blue-500 shadow-[0_4px_15px_rgba(59,130,246,0.15)]' },
                    { icon: PinterestIcon, urls: lastProfile.pinterest_url, label: 'Pinterest', brandStyles: 'border-red-600/40 bg-red-950/40 hover:bg-red-900/60 hover:border-red-500 text-red-500 shadow-[0_4px_15px_rgba(220,38,38,0.15)]' },
                    { icon: MediumIcon, urls: lastProfile.medium_url, label: 'Medium', brandStyles: 'border-gray-400/40 bg-gray-950/50 hover:bg-gray-800/80 hover:border-gray-300 text-gray-200 shadow-[0_4px_15px_rgba(229,231,235,0.15)]' },
                    { icon: ThreadsIcon, urls: lastProfile.threads_url, label: 'Threads', brandStyles: 'border-gray-500/40 bg-gray-900/50 hover:bg-gray-800/80 hover:border-gray-400 text-gray-300 shadow-[0_4px_15px_rgba(156,163,175,0.15)]' },
                    { icon: SteamIcon, urls: lastProfile.steam_url, label: 'Steam', brandStyles: 'border-blue-800/40 bg-blue-950/50 hover:bg-blue-900/60 hover:border-blue-600 text-blue-400 shadow-[0_4px_15px_rgba(30,64,175,0.15)]' },
                ];

                // Separate: found profiles vs search fallbacks
                const foundEntries = allPlatforms.filter(e => e.urls);
                const searchEntries = allPlatforms.filter(e => !e.urls && searchUrls[e.label]);

                // Mention-type entries (Tinder, Bumble, Discord)
                const mentionEntries = [
                    { icon: TinderIcon, urls: lastProfile.tinder_mention, label: 'Tinder', isMention: true, brandStyles: 'border-orange-500/40 bg-orange-950/40 hover:bg-orange-900/60 hover:border-orange-400 text-orange-400 shadow-[0_4px_15px_rgba(249,115,22,0.15)]' },
                    { icon: BumbleIcon, urls: lastProfile.bumble_mention, label: 'Bumble', isMention: true, brandStyles: 'border-amber-500/40 bg-amber-950/40 hover:bg-amber-900/60 hover:border-amber-400 text-amber-400 shadow-[0_4px_15px_rgba(245,158,11,0.15)]' },
                    { icon: DiscordIcon, urls: lastProfile.discord_mention, label: 'Discord', isMention: true, brandStyles: 'border-violet-500/40 bg-violet-950/40 hover:bg-violet-900/60 hover:border-violet-400 text-violet-400 shadow-[0_4px_15px_rgba(139,92,246,0.15)]' },
                ].filter(e => e.urls);

                const socialEntries: any[] = [...foundEntries, ...mentionEntries];

                // Add phone numbers if found
                if (lastProfile.phone_numbers && lastProfile.phone_numbers.length > 0) {
                    socialEntries.push({
                        icon: PhoneIcon,
                        urls: lastProfile.phone_numbers.join(', '),
                        label: 'Phone',
                        brandStyles: 'border-emerald-500/40 bg-emerald-950/40 hover:bg-emerald-900/60 hover:border-emerald-400 text-emerald-400 shadow-[0_4px_15px_rgba(52,211,153,0.15)]',
                    });
                }

                return (
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8, delay: 0.3, ease: 'easeOut' }}
                        className="fixed z-40 right-6 top-6 w-60 glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden"
                    >
                        <div className="p-2.5 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_5s_infinite]" />
                            <Globe className="w-4 h-4 text-cyan-400" />
                            <ScrambleText text="Network Nodes" className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
                            <span className="ml-auto text-[8px] font-mono bg-cyan-400/10 text-cyan-400 px-1.5 py-0.5 rounded-full border border-cyan-500/30">{socialEntries.length + searchEntries.length}</span>
                        </div>
                        <div className="p-2 space-y-1.5 overflow-y-auto max-h-[80vh] custom-scrollbar">
                            <AnimatePresence>
                                {/* Empty state when no social profiles found */}
                                {socialEntries.length === 0 && (
                                    <motion.div
                                        key="no-profiles"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="flex flex-col items-center gap-2 py-4 opacity-50"
                                    >
                                        <Globe className="w-5 h-5 text-cyan-500" />
                                        <span className="text-[9px] font-mono text-cyan-500/60 text-center">No social profiles detected</span>
                                    </motion.div>
                                )}
                                {/* Network Nodes Section */}
                                {socialEntries.flatMap(({ icon: Icon, urls, label, brandStyles, isMention }: any) => {
                                    if (!urls) return [];

                                    // Phone numbers & mentions: single non-link entry
                                    if (label === 'Phone' || isMention) {
                                        return [(
                                            <motion.div
                                                key={label}
                                                initial={{ opacity: 0, x: 20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                className={`flex items-center gap-2 p-2 rounded-xl border transition-all ${brandStyles}`}
                                            >
                                                <Icon className="w-4 h-4 shrink-0" />
                                                <div className="flex flex-col overflow-hidden">
                                                    <div className="flex items-center gap-1">
                                                        <span className="text-[11px] text-white font-bold font-mono tracking-wider drop-shadow-sm">{label}</span>
                                                        {isMention && <span className="text-[7px] font-mono bg-white/10 px-1 rounded">MENTION</span>}
                                                    </div>
                                                    <span className="text-[8px] opacity-60 font-mono truncate">{typeof urls === 'string' ? urls.substring(0, 40) : urls}</span>
                                                </div>
                                            </motion.div>
                                        )];
                                    }

                                    // Standard clickable URL entries (only valid http/https URLs)
                                    const parsedUrls = urls.split(',').map((u: string) => u.trim()).filter((u: string) => {
                                        try { const p = new URL(u); return p.protocol === 'http:' || p.protocol === 'https:'; }
                                        catch { return false; }
                                    });
                                    if (parsedUrls.length === 0) return [];
                                    return parsedUrls.map((singleUrl: string, idx: number) => {
                                        const username = singleUrl.replace(/\/+$/, '').split('/').pop() || '';
                                        const displayLabel = parsedUrls.length > 1 ? `@${username}` : label;
                                        return (
                                            <motion.a
                                                key={`${label}-${idx}`}
                                                href={singleUrl}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                initial={{ opacity: 0, x: 20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: idx * 0.05 }}
                                                className={`flex items-center gap-2 p-2 rounded-xl border transition-all group/link ${brandStyles}`}
                                                whileHover={{ x: -3, scale: 1.02 }}
                                                whileTap={{ scale: 0.98 }}
                                            >
                                                <Icon className="w-4 h-4 transition-colors group-hover/link:text-white shrink-0" />
                                                <span className="text-[11px] text-white font-bold font-mono tracking-wider drop-shadow-sm truncate">{displayLabel}</span>
                                            </motion.a>
                                        );
                                    });
                                })}

                                {/* Search Fallback Section — platforms without found profiles */}
                                {searchEntries.length > 0 && (
                                    <motion.div
                                        key="search-fallbacks"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="flex flex-col gap-1.5"
                                    >
                                        <div className="pt-2 pb-1 border-t border-cyan-500/10 mt-1">
                                            <div className="flex items-center gap-2 px-1">
                                                <Search className="w-3 h-3 text-cyan-500/50" />
                                                <span className="text-[8px] font-bold font-mono tracking-widest text-cyan-500/50 uppercase">Search on Platform</span>
                                            </div>
                                        </div>
                                        {searchEntries.map(({ icon: Icon, label, brandStyles }: any, idx: number) => (
                                            <motion.a
                                                key={`search-${label}`}
                                                href={searchUrls[label]}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                initial={{ opacity: 0, x: 10 }}
                                                animate={{ opacity: 0.7, x: 0 }}
                                                transition={{ delay: idx * 0.03 }}
                                                className="flex items-center gap-2 p-1.5 rounded-lg border border-white/10 bg-white/[0.03] hover:bg-white/[0.08] hover:opacity-100 hover:border-cyan-500/30 transition-all group/search"
                                                whileHover={{ x: -2, scale: 1.02 }}
                                            >
                                                <Icon className="w-3.5 h-3.5 opacity-50 group-hover/search:opacity-80 shrink-0" />
                                                <span className="text-[10px] text-white/50 font-mono tracking-wider truncate group-hover/search:text-white/70">{label}</span>
                                                <span className="text-[7px] font-mono bg-cyan-500/10 text-cyan-400/50 px-1.5 py-0.5 rounded ml-auto shrink-0 group-hover/search:bg-cyan-500/20 group-hover/search:text-cyan-400/80">SEARCH</span>
                                            </motion.a>
                                        ))}
                                    </motion.div>
                                )}

                                {/* Intelligence Sources Section */}
                                {lastProfile.sources && lastProfile.sources.length > 0 && (
                                    <motion.div
                                        key="intelligence-sources"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        className="flex flex-col gap-2"
                                    >
                                        <div className="pt-2 pb-1 border-t border-cyan-500/20 mt-2">
                                            <div className="flex items-center gap-2 px-1">
                                                <TerminalSquare className="w-3.5 h-3.5 text-cyan-400" />
                                                <ScrambleText text="Intelligence Sources" className="text-[9px] font-bold font-mono tracking-widest text-cyan-500/80 uppercase" />
                                            </div>
                                        </div>
                                        {lastProfile.sources.slice(0, 4).map((source, idx) => (
                                            <motion.a
                                                key={`source-${idx}`}
                                                href={source.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                initial={{ opacity: 0, x: 20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: 0.2 + idx * 0.05 }}
                                                className="flex flex-col gap-0.5 p-2.5 rounded-xl border border-cyan-500/20 bg-cyan-950/40 hover:bg-cyan-900/60 hover:border-cyan-400/50 transition-all group/source"
                                                whileHover={{ x: -3, scale: 1.02 }}
                                                whileTap={{ scale: 0.98 }}
                                            >
                                                <div className="flex items-center gap-1.5 overflow-hidden">
                                                    <Globe className="w-3 h-3 text-cyan-500/60 group-hover/source:text-cyan-400" />
                                                    <span className="text-[10px] text-cyan-100/90 font-bold font-mono truncate">{source.title}</span>
                                                </div>
                                                <span className="text-[8px] text-cyan-500/50 truncate pl-4 font-mono">{(() => { try { return new URL(source.url).hostname; } catch { return source.url.substring(0, 30); } })()}</span>
                                            </motion.a>
                                        ))}
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </motion.div>
                );
            })()}

            {/* Floating Atmospheric Widget (Between Chat and Right Sidebar) */}
            {(() => {
                if (!lastProfile || !lastProfile.weather_info) return null;

                const weather = lastProfile.weather_info;
                const isSunny = weather && (weather.temperature > 20 || weather.description.toLowerCase().includes('clear') || weather.description.toLowerCase().includes('sunny'));

                return (
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8, delay: 0.3, ease: 'easeOut' }}
                        className="fixed z-40 right-[17rem] top-6 w-56 glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden pointer-events-auto group/weather"
                    >
                        {/* Weather Header */}
                        <div className="p-3 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_5s_infinite]" />
                            <Cloud className="w-4 h-4 text-cyan-400" />
                            <span className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan">Weather Scan</span>
                        </div>

                        <div className="p-3 flex flex-col gap-3">
                            {/* Decorative scan line */}
                            <div className="absolute top-0 left-0 w-full h-0.5 bg-cyan-400/30 animate-[scan_3s_linear_infinite]" />

                            {/* Weather Icon / Environment Display */}
                            <div className="relative h-24 w-full rounded-xl bg-gradient-to-b from-black/40 to-cyan-900/20 border border-white/5 flex items-center justify-center overflow-hidden">
                                {isSunny ? (
                                    <div className="relative">
                                        <motion.div
                                            animate={{ rotate: 360 }}
                                            transition={{ repeat: Infinity, duration: 20, ease: "linear" }}
                                            className="absolute inset-0 bg-yellow-400/20 blur-2xl rounded-full scale-125"
                                        />
                                        <Sun className="w-10 h-10 text-yellow-400 drop-shadow-[0_0_12px_rgba(250,204,21,0.7)] relative z-10" />
                                    </div>
                                ) : (
                                    <div className="relative">
                                        <motion.div
                                            animate={{ x: [-10, 10, -10] }}
                                            transition={{ repeat: Infinity, duration: 8, ease: "easeInOut" }}
                                            className="absolute -top-2 -left-4 opacity-50"
                                        >
                                            <Cloud className="w-10 h-10 text-slate-400" />
                                        </motion.div>
                                        <Cloud className="w-14 h-14 text-slate-300 drop-shadow-[0_0_10px_rgba(203,213,225,0.5)] relative z-10" />
                                    </div>
                                )}

                                {/* Temperature Overlay */}
                                {weather && (
                                    <div className="absolute bottom-2 right-3 flex items-center gap-1">
                                        <Thermometer className="w-3 h-3 text-cyan-400" />
                                        <span className="text-sm font-orbitron font-black text-white glow-white">{weather.temperature}°C</span>
                                    </div>
                                )}
                            </div>

                            {/* Location & Status */}
                            <div className="space-y-1">
                                <div className="flex items-center gap-1.5 overflow-hidden">
                                    <MapPin className="w-3 h-3 text-cyan-400 shrink-0" />
                                    <span className="text-[10px] font-black font-orbitron tracking-widest text-white uppercase truncate drop-shadow-sm">
                                        {lastProfile.location_city || "Unknown Node"}
                                    </span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                    <div className={`w-1 h-1 rounded-full ${weather ? 'bg-cyan-400 animate-pulse' : 'bg-red-500'}`} />
                                    <span className={`text-[8px] font-bold font-mono tracking-widest uppercase ${weather ? 'text-cyan-400 glow-cyan' : 'text-red-400'}`}>
                                        {weather?.description || "OFFLINE"}
                                    </span>
                                </div>
                            </div>

                            {/* Wind speed if available */}
                            {weather?.wind_speed && (
                                <div className="pt-2 border-t border-cyan-500/10 flex justify-between items-center opacity-70">
                                    <span className="text-[9px] font-mono text-cyan-500 uppercase tracking-tighter">Atmospheric Flow</span>
                                    <div className="flex items-center gap-1">
                                        <Wind className="w-3.5 h-3.5 text-cyan-300" />
                                        <span className="text-[10px] font-mono font-bold text-white">{weather.wind_speed} <span className="text-[8px]">km/h</span></span>
                                    </div>
                                </div>
                            )}

                            {/* Hover effect highlight */}
                            <div className="absolute inset-0 border-2 border-transparent group-hover/weather:border-cyan-400/20 rounded-2xl transition-all duration-500" />
                        </div>
                    </motion.div>
                );
            })()}

            {/* Social Gauge Widget */}
            {(() => {
                if (!lastProfile || typeof lastProfile.social_media_score === 'undefined') return null;

                return (
                    <SocialGauge
                        score={lastProfile.social_media_score}
                        lastActive={lastProfile.last_activity_summary}
                        breakdown={lastProfile.social_media_score_breakdown}
                        platformActivity={lastProfile.platform_activity}
                    />
                );
            })()}

            {/* Sentiment Psychological Profiler Widget (Under Social Gauge) */}
            {(() => {
                if (!lastProfile || !lastProfile.sentiment_analysis) return null;

                // Adjust positioning dynamically (assuming SocialGauge takes up some space, we place this right below it)
                return (
                    <motion.div
                        initial={{ opacity: 0, x: -50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8, delay: 0.6, ease: 'easeOut' }}
                        className="fixed z-40 left-6 bottom-16 w-64 pointer-events-auto"
                    >
                        <SentimentGauge data={lastProfile.sentiment_analysis as any} />
                    </motion.div>
                );
            })()}

            {/* Messages Area */}
            <motion.div
                initial={{ paddingTop: "52vh", paddingBottom: "8rem" }}
                animate={{
                    paddingTop: messages.length === 0 ? "52vh" : "8rem",
                    paddingBottom: messages.length === 0 ? "8rem" : "9rem"
                }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="flex-1 overflow-y-auto px-4 scroll-smooth"
            >
                <div className="max-w-4xl mx-auto space-y-8">
                    <AnimatePresence initial={false}>
                        {messages.map((message, index) => (
                            <motion.div
                                key={message.id}
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
                                                    strong: ({ children, ...props }) => {
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
                                                    p: ({ children, ...props }) => {
                                                        const isImageContainer = React.Children.toArray(children).some(
                                                            (child) => React.isValidElement(child) && (child as React.ReactElement<any>).props.node?.tagName === 'img'
                                                        );
                                                        if (isImageContainer) {
                                                            return <div className="flex flex-wrap gap-4 mb-5 items-center justify-start">{children}</div>;
                                                        }
                                                        return <p className="leading-normal text-gray-200 mb-2 last:mb-0" {...props}>{children}</p>;
                                                    },
                                                    ul: ({ ...props }) => <ul className="list-none space-y-1 mb-2" {...props} />,
                                                    li: ({ ...props }) => (
                                                        <li className="flex gap-2">
                                                            <span className="text-cyan-500 mt-0.5">&#9657;</span>
                                                            <span className="text-gray-300" {...props} />
                                                        </li>
                                                    ),
                                                    img: ({ ...props }) => {
                                                        const src = typeof props.src === 'string' ? props.src : '';
                                                        const isWikiLogo = src.includes('wikipedia') && src.endsWith('.png');
                                                        if (isWikiLogo) return null; // Filter out rogue wikipedia textual logos
                                                        return (
                                                            <span className="inline-block shrink-0 rounded-2xl overflow-hidden border-2 border-cyan-500/50 w-32 h-32 sm:w-40 sm:h-40 shadow-[0_0_20px_rgba(0,255,255,0.25)] ring-1 ring-cyan-300/20 transition-transform hover:scale-105">
                                                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                                                <img
                                                                    className="w-full h-full object-cover object-top"
                                                                    {...props}
                                                                    alt={props.alt || "Profile Image"}
                                                                    onLoad={(e) => {
                                                                        const target = e.target as HTMLImageElement;
                                                                        // unavatar.io default generic fallback images usually render at 400x400 dimension exactly
                                                                        if (target.src.includes('unavatar.io') && target.naturalWidth === 400 && target.naturalHeight === 400) {
                                                                            const spanWrapper = target.parentElement;
                                                                            if (spanWrapper) spanWrapper.style.display = 'none';
                                                                            target.style.display = 'none';
                                                                        }
                                                                    }}
                                                                    onError={(e) => {
                                                                        const target = e.target as HTMLImageElement;
                                                                        const spanWrapper = target.parentElement;
                                                                        if (spanWrapper) {
                                                                            spanWrapper.style.display = 'none';
                                                                        }
                                                                        target.style.display = 'none';
                                                                    }}
                                                                />
                                                            </span>
                                                        );
                                                    },
                                                    a: ({ ...props }) => <a className="text-blue-400 hover:text-cyan-300 underline underline-offset-4 transition-colors" target="_blank" rel="noopener noreferrer" {...props} />
                                                }}
                                            >
                                                {message.content}
                                            </ReactMarkdown>
                                        </div>
                                        {message.profileData && (
                                            <div className="mt-4">
                                                <ProfileCard profile={message.profileData} />
                                                {message.profileData.version_history && message.profileData.version_history.snapshot_count >= 2 && (
                                                    <VersionHistory report={message.profileData.version_history} />
                                                )}
                                                {message.profileData.face_match_results && message.profileData.face_match_results.total_comparisons > 0 && (
                                                    <FaceMatch report={message.profileData.face_match_results} />
                                                )}
                                                <div className="mt-3 flex flex-col md:flex-row items-end justify-between gap-3 text-right">
                                                    <span className="text-gray-400 italic text-xs max-w-sm">
                                                        If this profile looks correct, save it to the database for quick access later.
                                                    </span>
                                                    {!message.isSaved ? (
                                                        <button
                                                            onClick={() => handleApprove(index, message.profileData!)}
                                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-900/40 hover:border-cyan-400 transition-colors shadow-[0_0_10px_rgba(0,255,255,0.1)] shrink-0"
                                                        >
                                                            <Save className="w-4 h-4" />
                                                            <span className="text-sm font-semibold tracking-wide">Save</span>
                                                        </button>
                                                    ) : (
                                                        <div className="flex items-center gap-1.5 px-3 py-1.5 text-green-400 font-medium shrink-0">
                                                            <CheckCircle className="w-5 h-5" />
                                                            <span className="text-sm">Saved to DB</span>
                                                        </div>
                                                    )}
                                                </div>

                                                {/* RAG Interactive Chat Mode (Only for the latest profile) */}
                                                {index === messages.length - 1 && (
                                                    <RagInteractionPanel profileName={message.profileData.name} />
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
            </motion.div>

            {/* Futuristic Floating Input Bar */}
            <ChatInputBar />
        </div>
    );
}
