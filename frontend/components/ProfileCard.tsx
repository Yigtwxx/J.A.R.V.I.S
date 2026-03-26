'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { SearchResponse } from '@/types/profile';
import { User, Users, ChevronRight, Activity, AlertTriangle } from 'lucide-react';
import dynamic from 'next/dynamic';
import GlitchText from '@/components/ui/GlitchText';

function extractUsername(url: string): string {
    try {
        const pathname = new URL(url).pathname.replace(/\/+$/, '');
        const segments = pathname.split('/').filter(Boolean);
        return segments.length > 0 ? segments[segments.length - 1] : url;
    } catch {
        return url;
    }
}

// ForceGraph MUST be loaded dynamically to avoid SSR 'window is not defined' error
const NetworkGraph = dynamic(() => import('@/components/NetworkGraph'), { ssr: false });
const SecurityScanWidget = dynamic(() => import('@/components/SecurityScanWidget'), { ssr: false });

interface ProfileCardProps {
    profile: SearchResponse;
}

function ProfileCard({ profile }: ProfileCardProps) {
    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            whileHover={{ y: -5 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="w-full relative mt-4 group"
        >
            {/* Tech Corner Accents */}
            <div className="absolute top-0 left-0 w-10 h-10 border-t-2 border-l-2 border-cyan-400 rounded-tl-xl opacity-80 shadow-[0_0_15px_rgba(0,255,255,0.4)]" />
            <div className="absolute bottom-0 right-0 w-10 h-10 border-b-2 border-r-2 border-blue-500 rounded-br-xl opacity-80 shadow-[0_0_15px_rgba(10,102,255,0.4)]" />

            <div className="glass-3d rounded-xl p-8 glow-border overflow-hidden relative border-cyan-400/50 animate-depth-breathe">
                {/* Subtle Background Elements */}
                <div className="absolute -top-32 -right-32 w-64 h-64 bg-cyan-400/15 rounded-full blur-[80px] pointer-events-none" />

                {/* Header */}
                <div className="flex items-center gap-5 mb-8 border-b border-cyan-400/30 pb-5 relative">
                    <div className="relative">
                        <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-cyan-400/20 to-blue-600/20 border border-cyan-400/50 flex items-center justify-center relative z-10 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.3)]">
                            <User className="w-8 h-8 text-white glow-white" />
                        </div>
                        {/* Avatar Glow */}
                        <div className="absolute inset-0 bg-cyan-400/30 blur-lg rounded-xl" />
                    </div>
                    <div>
                        <div className="flex items-center gap-3 mb-1">
                            <Activity className="w-5 h-5 text-cyan-400 animate-pulse glow-cyan" />
                            <h3 className="text-3xl font-orbitron font-black text-white tracking-widest uppercase drop-shadow-lg">
                                <GlitchText text={profile.name} interval={4000} />
                            </h3>
                        </div>
                        <div className="flex items-center gap-2 text-cyan-300 text-[11px] font-bold font-mono tracking-widest uppercase glow-cyan mt-1">
                            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse box-shadow-[0_0_10px_cyan]" />
                            Target Profile Identified
                        </div>
                    </div>
                </div>


                {/* Content Area */}
                <div className="flex flex-col gap-10 relative">
                    {/* Bio Section */}
                    {profile.description && (
                        <div className="max-w-3xl">
                            <div className="flex items-center gap-2 mb-3">
                                <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase drop-shadow-md glow-cyan">Extracted Bio</h4>
                            </div>
                            <p className="text-slate-100 font-medium text-[15px] pl-6 border-l-2 border-cyan-500/30 ml-2 leading-relaxed">
                                {profile.description}
                            </p>
                        </div>
                    )}

                    {/* Cross Validation Warnings */}
                    {profile.cross_validation_issues && profile.cross_validation_issues.length > 0 && (
                        <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-5 relative overflow-hidden group/warning">
                            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-orange-500/50 to-transparent" />
                            <div className="flex items-start gap-4 relative z-10">
                                <div className="p-2 bg-orange-500/20 rounded-lg shrink-0 mt-0.5 border border-orange-500/20">
                                    <AlertTriangle className="w-5 h-5 text-orange-400 group-hover/warning:animate-pulse" />
                                </div>
                                <div className="space-y-3 flex-1">
                                    <h4 className="text-orange-400 font-orbitron font-bold text-sm tracking-[0.1em] uppercase drop-shadow-md">
                                        Data Integrity Warning
                                    </h4>
                                    <ul className="space-y-2">
                                        {profile.cross_validation_issues.map((issue, idx) => (
                                            <li key={idx} className="flex gap-2 text-orange-200/90 text-sm leading-relaxed">
                                                <span className="text-orange-500 font-bold mt-0.5">›</span>
                                                {issue}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Correlated Targets */}
                    {profile.similar_profiles && profile.similar_profiles.length > 0 && (
                        <div>
                            <div className="flex items-center gap-2 mb-4">
                                <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase flex items-center gap-2 drop-shadow-md glow-cyan">
                                    <Users className="w-4 h-4 text-cyan-400" />
                                    Correlated Targets
                                </h4>
                            </div>
                            <div className="flex flex-wrap gap-2.5 pl-6">
                                {profile.similar_profiles.map((name, index) => (
                                    <span
                                        key={index}
                                        className="px-3.5 py-1.5 rounded-lg bg-blue-900/40 border border-blue-400/40 text-[13px] text-white font-bold font-mono tracking-widest shadow-[0_0_15px_rgba(10,102,255,0.2)] hover:bg-blue-800/60 transition-colors"
                                    >
                                        {name}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Knowledge Graph / Network Connections */}
                    {(() => {
                        const platformMap: { key: keyof SearchResponse; label: string }[] = [
                            { key: 'github_url',     label: 'GitHub' },
                            { key: 'instagram_url',  label: 'Instagram' },
                            { key: 'twitter_url',    label: 'Twitter/X' },
                            { key: 'linkedin_url',   label: 'LinkedIn' },
                            { key: 'spotify_url',    label: 'Spotify' },
                            { key: 'tiktok_url',     label: 'TikTok' },
                            { key: 'snapchat_url',   label: 'Snapchat' },
                            { key: 'tumblr_url',     label: 'Tumblr' },
                            { key: 'youtube_url',    label: 'YouTube' },
                            { key: 'reddit_url',     label: 'Reddit' },
                            { key: 'facebook_url',   label: 'Facebook' },
                            { key: 'pinterest_url',  label: 'Pinterest' },
                            { key: 'medium_url',     label: 'Medium' },
                            { key: 'threads_url',    label: 'Threads' },
                            { key: 'steam_url',      label: 'Steam' },
                        ];
                        const platformNodes = platformMap.flatMap(({ key, label }) => {
                            const val = profile[key];
                            if (!val) return [];
                            const urls = (val as string).split(',').map(u => u.trim()).filter(u => {
                                try { return ['http:', 'https:'].includes(new URL(u).protocol); }
                                catch { return false; }
                            });
                            if (urls.length === 0) return [];
                            const activity = profile.platform_activity?.[label.toLowerCase().replace('/x', '')] ?? undefined;
                            return urls.map(url => ({
                                name: urls.length > 1 ? `${label} (${extractUsername(url)})` : label,
                                url,
                                activity,
                            }));
                        });
                        const hasConnections = profile.network_connections && profile.network_connections.length > 0;
                        if (!hasConnections && platformNodes.length === 0) return null;
                        return (
                            <div className="mt-4">
                                <NetworkGraph
                                    targetName={profile.name}
                                    connections={profile.network_connections ?? []}
                                    platforms={platformNodes}
                                />
                            </div>
                        );
                    })()}

                    {/* Threat Intelligence / Dark Web Monitoring */}
                    <SecurityScanWidget
                        emails={profile.email_addresses}
                        dataBreaches={profile.data_breaches}
                    />
                </div>
            </div>
        </motion.div>
    );
}

export default React.memo(ProfileCard);
