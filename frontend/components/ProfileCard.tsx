'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { SearchResponse } from '@/types/profile';
import { Github, Instagram, Twitter, Linkedin, User, Users, ChevronRight, Activity } from 'lucide-react';

interface ProfileCardProps {
    profile: SearchResponse;
}

export default function ProfileCard({ profile }: ProfileCardProps) {
    const socialLinks = [
        { icon: Github, url: profile.github_url, label: 'GitHub' },
        { icon: Instagram, url: profile.instagram_url, label: 'Instagram' },
        { icon: Twitter, url: profile.twitter_url, label: 'X (Twitter)' },
        { icon: Linkedin, url: profile.linkedin_url, label: 'LinkedIn' },
    ].filter(link => link.url);

    return (
        <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="w-full relative mt-4 group"
        >
            {/* Tech Corner Accents */}
            <div className="absolute top-0 left-0 w-10 h-10 border-t-2 border-l-2 border-cyan-400 rounded-tl-xl opacity-80 shadow-[0_0_15px_rgba(0,255,255,0.4)]" />
            <div className="absolute bottom-0 right-0 w-10 h-10 border-b-2 border-r-2 border-blue-500 rounded-br-xl opacity-80 shadow-[0_0_15px_rgba(10,102,255,0.4)]" />

            <div className="glass-strong rounded-xl p-8 glow-border overflow-hidden relative border-cyan-400/50">
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
                                {profile.name}
                            </h3>
                        </div>
                        <div className="flex items-center gap-2 text-cyan-300 text-[11px] font-bold font-mono tracking-widest uppercase glow-cyan mt-1">
                            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse box-shadow-[0_0_10px_cyan]" />
                            Target Profile Identified
                        </div>
                    </div>
                </div>



                {/* Description Grid */}
                {profile.description && (
                    <div className="mb-8">
                        <div className="flex items-center gap-2 mb-3">
                            <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                            <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase drop-shadow-md glow-cyan">Extracted Bio</h4>
                        </div>
                        <p className="text-slate-100 font-medium text-[15px] pl-6 border-l-2 border-cyan-500/30 ml-2 leading-relaxed">{profile.description}</p>
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative">
                    {/* Social Links */}
                    {socialLinks.length > 0 && (
                        <div>
                            <div className="flex items-center gap-2 mb-4">
                                <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase drop-shadow-md glow-cyan">Network Nodes</h4>
                            </div>
                            <div className="grid grid-cols-2 gap-3 pl-6">
                                {socialLinks.map(({ icon: Icon, url, label }) => {
                                    // Determine brand-specific colors
                                    let brandStyles = "border-cyan-400/40 bg-cyan-950/50 hover:bg-cyan-900/80 hover:border-cyan-400 text-cyan-400";
                                    let platformKey = '';

                                    if (label === 'Instagram') {
                                        brandStyles = "border-pink-500/40 bg-fuchsia-950/40 hover:bg-fuchsia-900/60 hover:border-pink-400 text-pink-400 shadow-[0_4px_15px_rgba(236,72,153,0.15)]";
                                        platformKey = 'instagram';
                                    } else if (label === 'X (Twitter)') {
                                        brandStyles = "border-slate-500/40 bg-slate-900/50 hover:bg-slate-800/80 hover:border-slate-300 text-slate-300 shadow-[0_4px_15px_rgba(148,163,184,0.15)]";
                                        platformKey = 'twitter';
                                    } else if (label === 'LinkedIn') {
                                        brandStyles = "border-blue-500/40 bg-blue-950/50 hover:bg-blue-900/60 hover:border-blue-400 text-blue-400 shadow-[0_4px_15px_rgba(59,130,246,0.15)]";
                                        platformKey = 'linkedin';
                                    } else if (label === 'GitHub') {
                                        brandStyles = "border-gray-500/40 bg-gray-900/50 hover:bg-gray-800/80 hover:border-gray-400 text-gray-300 shadow-[0_4px_15px_rgba(156,163,175,0.15)]";
                                        platformKey = 'github';
                                    }

                                    return (
                                        <motion.a
                                            key={label}
                                            href={url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className={`flex items-center gap-3 p-3.5 rounded-xl border transition-all group/link ${brandStyles}`}
                                            whileHover={{ x: 4, scale: 1.02 }}
                                            whileTap={{ scale: 0.98 }}
                                        >
                                            <Icon className="w-5 h-5 transition-colors group-hover/link:text-white" />
                                            <span className="text-sm text-white font-bold font-mono tracking-wider drop-shadow-sm">{label}</span>
                                        </motion.a>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Similar Profiles */}
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
                                        className="px-3.5 py-1.5 rounded-lg bg-blue-900/50 border border-blue-400/60 text-[13px] text-white font-bold font-mono tracking-widest shadow-[0_0_15px_rgba(10,102,255,0.3)]"
                                    >
                                        {name}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </motion.div>
    );
}
