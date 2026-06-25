'use client';

import React, { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { motion, AnimatePresence } from 'framer-motion';
import { TerminalSquare, Github, Instagram, Twitter, Linkedin, Globe, MapPin, Thermometer, Cloud, Sun, Wind, Search, ChevronRight, ChevronLeft, Bot, Radar, ShieldAlert, Archive, GraduationCap } from 'lucide-react';
import dynamic from 'next/dynamic';
import { useChatStore } from '@/store/chatStore';
import ScrambleText from '@/components/ui/ScrambleText';
import LiveStatusMonitor from '@/components/chat/LiveStatusMonitor';
import type { SearchResponse } from '@/types/profile';

// Custom Brand Icons
import { SpotifyIcon, TikTokIcon, SnapchatIcon, TumblrIcon, TinderIcon,
         BumbleIcon, YoutubeIcon, RedditIcon, FacebookIcon, PhoneIcon,
         PinterestIcon, MediumIcon, ThreadsIcon, SteamIcon, DiscordIcon } from '@/components/ui/Icons';

// Lazy-loaded heavy widgets
const SocialGauge = dynamic(() => import('@/components/SocialGauge'), { ssr: false });
const SentimentGauge = dynamic(() => import('@/components/SentimentGauge'), { ssr: false });
const AgentChatMode = dynamic(() => import('@/components/chat/AgentChatMode'), { ssr: false });

/* ──────────────────────────────────────────────────────────────────────────
 * Network Nodes panel — social profiles, search fallbacks & intelligence
 * sources. Logic preserved verbatim from the previous ChatInterface block.
 * ────────────────────────────────────────────────────────────────────────── */
function NetworkNodesPanel({ lastProfile }: { lastProfile: SearchResponse }) {
    // Generate username variations from the name for better search coverage
    const searchName = lastProfile.name || '';
    const generateNameVariations = (name: string): string[] => {
        const variations: string[] = [];
        const seen = new Set<string>();
        const addVar = (v: string) => {
            const lower = v.toLowerCase().trim();
            if (lower.length >= 3 && !seen.has(lower)) {
                seen.add(lower);
                variations.push(lower);
            }
        };

        // Turkish/diacritics -> ASCII normalization
        const asciiName = name.normalize('NFD').replace(new RegExp('[\\u0300-\\u036f]', 'g'), '').replace(/ı/g, 'i').replace(/İ/g, 'I');
        const parts = asciiName.trim().split(/\s+/).map(p => p.toLowerCase());

        if (parts.length >= 2) {
            const first = parts[0];
            const last = parts[parts.length - 1];
            addVar(first + last);           // yagmurozgan
            addVar(first + '.' + last);     // yagmur.ozgan
            addVar(first + '_' + last);     // yagmur_ozgan
            addVar(last + first);           // ozganyagmur
            addVar(first + last[0]);        // yagmuro
            addVar(first[0] + last);        // yozgan
            addVar(first + last + '1');     // yagmurozgan1
        } else if (parts.length === 1) {
            addVar(parts[0]);
        }

        // Also add the raw stripped form (remove all non-alphanumeric)
        const raw = name.toLowerCase().replace(/[^a-z0-9]/g, '');
        addVar(raw);

        return variations;
    };

    const nameVariations = generateNameVariations(searchName);
    const encoded = encodeURIComponent(searchName);

    // Platform search configs — use Google site: search for reliable top-3 results
    const platformSearchConfigs: Record<string, { sitePattern: string; nativeUrl?: string }> = {
        'GitHub':       { sitePattern: 'github.com', nativeUrl: `https://github.com/search?q=${encoded}&type=users` },
        'Instagram':    { sitePattern: 'instagram.com' },
        'X (Twitter)':  { sitePattern: 'x.com OR twitter.com', nativeUrl: `https://x.com/search?q=${encoded}&f=user` },
        'LinkedIn':     { sitePattern: 'linkedin.com/in', nativeUrl: `https://www.linkedin.com/search/results/people/?keywords=${encoded}` },
        'Spotify':      { sitePattern: 'open.spotify.com', nativeUrl: `https://open.spotify.com/search/${encoded}` },
        'TikTok':       { sitePattern: 'tiktok.com', nativeUrl: `https://www.tiktok.com/search/user?q=${encoded}` },
        'Snapchat':     { sitePattern: 'snapchat.com' },
        'Tumblr':       { sitePattern: 'tumblr.com' },
        'YouTube':      { sitePattern: 'youtube.com', nativeUrl: `https://www.youtube.com/results?search_query=${encoded}` },
        'Reddit':       { sitePattern: 'reddit.com/user', nativeUrl: `https://www.reddit.com/search/?q=${encoded}&type=user` },
        'Facebook':     { sitePattern: 'facebook.com', nativeUrl: `https://www.facebook.com/search/people/?q=${encoded}` },
        'Pinterest':    { sitePattern: 'pinterest.com', nativeUrl: `https://www.pinterest.com/search/users/?q=${encoded}` },
        'Medium':       { sitePattern: 'medium.com/@', nativeUrl: `https://medium.com/search?q=${encoded}` },
        'Threads':      { sitePattern: 'threads.net', nativeUrl: `https://www.threads.net/search?q=${encoded}&serp_type=default` },
        'Steam':        { sitePattern: 'steamcommunity.com', nativeUrl: `https://steamcommunity.com/search/users/#text=${encoded}` },
    };

    // Build search URLs using Google site: + name variations for top 3 results
    const searchUrls: Record<string, string> = {};
    for (const [label, config] of Object.entries(platformSearchConfigs)) {
        const googleQuery = `site:${config.sitePattern} ${searchName} ${nameVariations.slice(0, 3).join(' OR ')}`;
        searchUrls[label] = config.nativeUrl || `https://www.google.com/search?q=${encodeURIComponent(googleQuery)}&num=3`;
    }

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
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="w-full glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden"
        >
            <div className="p-2.5 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_5s_infinite]" />
                <Globe className="w-4 h-4 text-cyan-400" />
                <ScrambleText text="Network Nodes" className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
                <span className="ml-auto text-[8px] font-mono bg-cyan-400/10 text-cyan-400 px-1.5 py-0.5 rounded-full border border-cyan-500/30">{socialEntries.length + searchEntries.length}</span>
            </div>
            <div className="p-2.5 space-y-2">
                <AnimatePresence>
                    {/* Empty state when no social profiles found */}
                    {socialEntries.length === 0 && searchEntries.length > 0 && (
                        <motion.div
                            key="no-verified"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="flex flex-col items-center gap-2 py-3 opacity-70"
                        >
                            <Search className="w-4 h-4 text-amber-400" />
                            <span className="text-[9px] font-mono text-amber-400/80 text-center leading-tight">
                                No verified profiles found.<br/>
                                Use search links below to investigate.
                            </span>
                        </motion.div>
                    )}
                    {socialEntries.length === 0 && searchEntries.length === 0 && (
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
                                    <span className="text-[6px] font-mono bg-green-500/20 text-green-400 px-1 py-0.5 rounded ml-auto shrink-0 border border-green-500/30">FOUND</span>
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
                            <div className="pt-3 pb-1.5 border-t border-cyan-500/15 mt-2">
                                <div className="flex items-center gap-2 px-1">
                                    <Search className="w-3 h-3 text-cyan-500/50" />
                                    <span className="text-[8px] font-bold font-mono tracking-widest text-cyan-500/50 uppercase">Search on Platform</span>
                                </div>
                                {nameVariations.length > 0 && (
                                    <div className="flex flex-wrap gap-1 px-1 mt-1">
                                        {nameVariations.slice(0, 3).map((v, i) => (
                                            <span key={i} className="text-[7px] font-mono bg-cyan-500/10 text-cyan-400/60 px-1 py-0.5 rounded border border-cyan-500/10">@{v}</span>
                                        ))}
                                    </div>
                                )}
                            </div>
                            {searchEntries.map(({ icon: Icon, label }: any, idx: number) => (
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
                        {lastProfile.sources && lastProfile.sources.length > 0 ? (
                            lastProfile.sources.slice(0, 4).map((source, idx) => (
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
                            ))
                        ) : (
                            <div className="text-[9px] font-mono text-cyan-500/40 px-2 py-3 text-center">
                                No indexed sources available for this query
                            </div>
                        )}
                    </motion.div>
                </AnimatePresence>
            </div>
        </motion.div>
    );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Weather Scan panel — atmospheric readout for the target location.
 * Logic preserved verbatim from the previous ChatInterface block.
 * ────────────────────────────────────────────────────────────────────────── */
function WeatherPanel({ lastProfile }: { lastProfile: SearchResponse }) {
    const weather = lastProfile.weather_info;
    if (!weather) return null;
    const isSunny = weather.temperature > 20 || weather.description.toLowerCase().includes('clear') || weather.description.toLowerCase().includes('sunny');

    return (
        <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="w-full glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden pointer-events-auto group/weather relative"
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
                    <div className="absolute bottom-2 right-3 flex items-center gap-1">
                        <Thermometer className="w-3 h-3 text-cyan-400" />
                        <span className="text-sm font-orbitron font-black text-white glow-white">{weather.temperature}°C</span>
                    </div>
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
                        <div className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse" />
                        <span className="text-[8px] font-bold font-mono tracking-widest uppercase text-cyan-400 glow-cyan">
                            {weather.description || "OFFLINE"}
                        </span>
                    </div>
                </div>

                {/* Wind speed if available */}
                {weather.wind_speed && (
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
}

/* ──────────────────────────────────────────────────────────────────────────
 * Domain Intel panel — public RDAP/WHOIS + DNS + Certificate Transparency
 * intelligence for domains derived from the subject's email/website.
 * ────────────────────────────────────────────────────────────────────────── */
function DomainIntelPanel({ lastProfile }: { lastProfile: SearchResponse }) {
    const t = useTranslations('domainIntel');
    const domains = lastProfile.domain_intel;
    if (!domains || domains.length === 0) return null;

    const fmtDate = (iso?: string | null) => (iso ? iso.slice(0, 10) : '—');

    return (
        <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="w-full glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden pointer-events-auto"
        >
            {/* Header */}
            <div className="p-3 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_5s_infinite]" />
                <Globe className="w-4 h-4 text-cyan-400" />
                <span className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan">{t('title')}</span>
            </div>

            <div className="p-3 flex flex-col gap-3 max-h-[26rem] overflow-y-auto custom-scrollbar">
                {domains.map((d, i) => (
                    <div key={`${d.domain}-${i}`} className="rounded-xl bg-black/30 border border-white/5 p-2.5 flex flex-col gap-1.5">
                        <div className="flex items-center gap-1.5">
                            <Globe className="w-3 h-3 text-cyan-400 shrink-0" />
                            <span className="text-[11px] font-black font-orbitron tracking-wide text-white truncate">{d.domain}</span>
                        </div>

                        {d.registrar && (
                            <div className="flex justify-between gap-2">
                                <span className="text-[9px] font-mono uppercase text-cyan-500/80 tracking-tighter">{t('registrar')}</span>
                                <span className="text-[10px] font-mono text-white/90 truncate text-right">{d.registrar}</span>
                            </div>
                        )}

                        <div className="flex justify-between gap-2">
                            <span className="text-[9px] font-mono uppercase text-cyan-500/80 tracking-tighter">{t('created')}</span>
                            <span className="text-[10px] font-mono text-white/90">{fmtDate(d.created)}</span>
                        </div>
                        <div className="flex justify-between gap-2">
                            <span className="text-[9px] font-mono uppercase text-cyan-500/80 tracking-tighter">{t('expires')}</span>
                            <span className="text-[10px] font-mono text-white/90">{fmtDate(d.expires)}</span>
                        </div>

                        {d.nameservers && d.nameservers.length > 0 && (
                            <div className="pt-1 border-t border-cyan-500/10">
                                <span className="text-[9px] font-mono uppercase text-cyan-500/80 tracking-tighter">{t('nameservers')}</span>
                                <div className="text-[10px] font-mono text-white/80 break-all">{d.nameservers.join(', ')}</div>
                            </div>
                        )}

                        {d.dns?.a && d.dns.a.length > 0 && (
                            <div className="flex justify-between gap-2">
                                <span className="text-[9px] font-mono uppercase text-cyan-500/80 tracking-tighter">{t('dns')} A</span>
                                <span className="text-[10px] font-mono text-white/90 break-all text-right">{d.dns.a.join(', ')}</span>
                            </div>
                        )}

                        {d.subdomains && d.subdomains.length > 0 && (
                            <div className="pt-1 border-t border-cyan-500/10">
                                <span className="text-[9px] font-mono uppercase text-cyan-500/80 tracking-tighter">{t('subdomains')} ({d.subdomains.length})</span>
                                <div className="text-[10px] font-mono text-white/70 break-all max-h-20 overflow-y-auto custom-scrollbar">
                                    {d.subdomains.slice(0, 15).join(', ')}
                                </div>
                            </div>
                        )}

                        {d.source_url && (
                            <a
                                href={d.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[9px] font-mono text-cyan-400/70 hover:text-cyan-300 underline truncate"
                            >
                                {t('publicNote')}
                            </a>
                        )}
                    </div>
                ))}
            </div>
        </motion.div>
    );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Sanctions panel — possible matches against PUBLIC watchlists (OFAC SDN).
 * Informational only; every hit carries a match score + verify note.
 * ────────────────────────────────────────────────────────────────────────── */
function SanctionsPanel({ lastProfile }: { lastProfile: SearchResponse }) {
    const t = useTranslations('sanctions');
    const hits = lastProfile.sanctions_hits;
    if (!hits || hits.length === 0) return null;

    return (
        <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="w-full glass-strong rounded-[1.5rem] border border-red-500/30 bg-red-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(255,0,0,0.08)] flex flex-col overflow-hidden pointer-events-auto"
        >
            <div className="p-3 border-b border-red-500/30 bg-red-900/40 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-red-400" />
                <span className="text-[10px] font-bold font-mono tracking-widest text-red-300 uppercase">{t('title')}</span>
            </div>
            <div className="p-3 flex flex-col gap-2 max-h-[26rem] overflow-y-auto custom-scrollbar">
                <p className="text-[9px] font-mono text-amber-300/80 italic">{t('disclaimer')}</p>
                {hits.map((h, i) => (
                    <div key={`${h.name}-${i}`} className="rounded-xl bg-black/30 border border-red-500/15 p-2.5 flex flex-col gap-1">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-black font-orbitron text-white truncate">{h.name}</span>
                            {typeof h.match_score === 'number' && (
                                <span className="text-[10px] font-mono text-red-300 shrink-0">{t('matchScore')} {Math.round(h.match_score * 100)}%</span>
                            )}
                        </div>
                        <div className="flex justify-between gap-2">
                            <span className="text-[9px] font-mono uppercase text-red-500/70">{t('list')}</span>
                            <span className="text-[10px] font-mono text-white/90 truncate text-right">{h.list_name || '—'}</span>
                        </div>
                        {h.program && (
                            <div className="flex justify-between gap-2">
                                <span className="text-[9px] font-mono uppercase text-red-500/70">{t('program')}</span>
                                <span className="text-[10px] font-mono text-white/80 truncate text-right">{h.program}</span>
                            </div>
                        )}
                        {h.source_url && (
                            <a href={h.source_url} target="_blank" rel="noopener noreferrer" className="text-[9px] font-mono text-red-400/70 hover:text-red-300 underline truncate">{t('viewSource')}</a>
                        )}
                    </div>
                ))}
            </div>
        </motion.div>
    );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Archive panel — public Wayback Machine snapshots of the subject's URLs.
 * ────────────────────────────────────────────────────────────────────────── */
function ArchivePanel({ lastProfile }: { lastProfile: SearchResponse }) {
    const t = useTranslations('archive');
    const snaps = lastProfile.archive_snapshots;
    if (!snaps || snaps.length === 0) return null;
    const fmt = (iso?: string | null) => (iso ? iso.slice(0, 10) : '—');

    return (
        <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="w-full glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden pointer-events-auto"
        >
            <div className="p-3 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2">
                <Archive className="w-4 h-4 text-cyan-400" />
                <span className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan">{t('title')}</span>
            </div>
            <div className="p-3 flex flex-col gap-2 max-h-[26rem] overflow-y-auto custom-scrollbar">
                {snaps.map((s, i) => (
                    <div key={`${s.snapshot_url}-${i}`} className="rounded-xl bg-black/30 border border-white/5 p-2.5 flex flex-col gap-1">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[10px] font-mono text-white/90 truncate">{s.url}</span>
                            <span className="text-[9px] font-mono text-cyan-400/70 shrink-0">{t('captured')} {fmt(s.timestamp)}</span>
                        </div>
                        <a href={s.snapshot_url} target="_blank" rel="noopener noreferrer" className="text-[9px] font-mono text-cyan-400/70 hover:text-cyan-300 underline truncate">{t('viewSnapshot')}</a>
                    </div>
                ))}
            </div>
        </motion.div>
    );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Scholarly panel — public academic records (Semantic Scholar/arXiv/Crossref).
 * ────────────────────────────────────────────────────────────────────────── */
function ScholarlyPanel({ lastProfile }: { lastProfile: SearchResponse }) {
    const t = useTranslations('scholarly');
    const records = lastProfile.scholarly_records;
    if (!records || records.length === 0) return null;

    return (
        <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="w-full glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden pointer-events-auto"
        >
            <div className="p-3 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2">
                <GraduationCap className="w-4 h-4 text-cyan-400" />
                <span className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan">{t('title')}</span>
            </div>
            <div className="p-3 flex flex-col gap-2 max-h-[26rem] overflow-y-auto custom-scrollbar">
                {records.map((r, i) => (
                    <div key={`${r.title}-${i}`} className="rounded-xl bg-black/30 border border-white/5 p-2.5 flex flex-col gap-1">
                        <span className="text-[11px] font-bold text-white leading-snug">{r.title}</span>
                        <div className="flex items-center gap-2 text-[9px] font-mono text-cyan-400/70">
                            {r.year && <span>{t('year')} {r.year}</span>}
                            {r.venue && <span className="truncate">· {r.venue}</span>}
                        </div>
                        {r.source_url && (
                            <a href={r.source_url} target="_blank" rel="noopener noreferrer" className="text-[9px] font-mono text-cyan-400/70 hover:text-cyan-300 underline truncate">{t('viewSource')}</a>
                        )}
                    </div>
                ))}
            </div>
        </motion.div>
    );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Intel Dock — consolidated right column. Replaces the previously scattered
 * fixed-position widgets (live monitor, network nodes, weather, gauges, agent).
 * ────────────────────────────────────────────────────────────────────────── */
export default function IntelDock() {
    const messages = useChatStore(state => state.messages);
    const isLoading = useChatStore(state => state.isLoading);
    const isAgentMode = useChatStore(state => state.isAgentMode);
    const [collapsed, setCollapsed] = useState(false);

    const lastProfile = useMemo(
        () => [...messages].reverse().find(m => m.role === 'assistant' && m.profileData)?.profileData,
        [messages]
    );

    const hasContent = isAgentMode || isLoading || !!lastProfile;
    if (!hasContent) return null;

    // Collapsed → slim re-open handle
    if (collapsed) {
        return (
            <div className="h-screen flex items-start justify-center pt-24 px-1.5 z-20">
                <button
                    onClick={() => setCollapsed(false)}
                    title="Expand intel dock"
                    className="w-9 h-16 rounded-l-xl glass-strong border border-cyan-500/30 flex items-center justify-center text-cyan-400 hover:text-cyan-200 hover:border-cyan-400/60 transition-all"
                >
                    <ChevronLeft className="w-4 h-4" />
                </button>
            </div>
        );
    }

    return (
        <motion.aside
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className={`h-screen flex flex-col ${isAgentMode ? 'w-[30rem]' : 'w-[21rem]'} shrink-0 pt-6 pb-6 pr-4 pl-1 z-20 transition-[width] duration-500`}
        >
            {/* Dock header / collapse control */}
            <div className="flex items-center gap-2 px-2 pb-3 shrink-0">
                {isAgentMode ? <Bot className="w-4 h-4 text-purple-400" /> : <Radar className="w-4 h-4 text-cyan-400" />}
                <span className={`text-[10px] font-bold font-orbitron tracking-[0.25em] uppercase ${isAgentMode ? 'text-purple-300' : 'text-cyan-300 glow-cyan'}`}>
                    {isAgentMode ? 'Agent Console' : 'Intel Dock'}
                </span>
                <button
                    onClick={() => setCollapsed(true)}
                    title="Collapse intel dock"
                    className="ml-auto p-1.5 rounded-lg text-cyan-500/50 hover:text-cyan-300 hover:bg-cyan-500/10 transition-all"
                >
                    <ChevronRight className="w-4 h-4" />
                </button>
            </div>

            {isAgentMode ? (
                <div className="flex-1 min-h-0 glass-strong rounded-[1.5rem] border border-purple-500/30 bg-gray-950/90 backdrop-blur-md shadow-[0_0_30px_rgba(168,85,247,0.1)] overflow-hidden">
                    <AgentChatMode />
                </div>
            ) : (
                <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar pr-1 space-y-4">
                    {isLoading && <LiveStatusMonitor />}
                    {!isLoading && lastProfile && (
                        <>
                            <NetworkNodesPanel lastProfile={lastProfile} />
                            {lastProfile.sanctions_hits && lastProfile.sanctions_hits.length > 0 && (
                                <SanctionsPanel lastProfile={lastProfile} />
                            )}
                            {lastProfile.domain_intel && lastProfile.domain_intel.length > 0 && (
                                <DomainIntelPanel lastProfile={lastProfile} />
                            )}
                            {lastProfile.archive_snapshots && lastProfile.archive_snapshots.length > 0 && (
                                <ArchivePanel lastProfile={lastProfile} />
                            )}
                            {lastProfile.scholarly_records && lastProfile.scholarly_records.length > 0 && (
                                <ScholarlyPanel lastProfile={lastProfile} />
                            )}
                            {lastProfile.weather_info && <WeatherPanel lastProfile={lastProfile} />}
                            {typeof lastProfile.social_media_score !== 'undefined' && (
                                <SocialGauge
                                    score={lastProfile.social_media_score}
                                    lastActive={lastProfile.last_activity_summary}
                                    breakdown={lastProfile.social_media_score_breakdown}
                                    platformActivity={lastProfile.platform_activity}
                                />
                            )}
                            {lastProfile.sentiment_analysis && (
                                <SentimentGauge data={lastProfile.sentiment_analysis as any} />
                            )}
                        </>
                    )}
                </div>
            )}
        </motion.aside>
    );
}
