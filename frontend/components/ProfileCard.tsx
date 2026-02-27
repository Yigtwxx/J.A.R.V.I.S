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
            <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-cyan-400 rounded-tl-xl opacity-50" />
            <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-blue-500 rounded-br-xl opacity-50" />

            <div className="glass-strong rounded-xl p-6 glow-border overflow-hidden relative">
                {/* Subtle Background Elements */}
                <div className="absolute -top-24 -right-24 w-48 h-48 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

                {/* Header */}
                <div className="flex items-center gap-4 mb-6 border-b border-cyan-500/10 pb-4 relative">
                    <div className="relative">
                        <div className="w-14 h-14 rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-400/30 flex items-center justify-center relative z-10 backdrop-blur-sm">
                            <User className="w-7 h-7 text-cyan-400" />
                        </div>
                        {/* Avatar Glow */}
                        <div className="absolute inset-0 bg-cyan-400/20 blur-md rounded-lg" />
                    </div>
                    <div>
                        <div className="flex items-center gap-2 mb-1">
                            <Activity className="w-4 h-4 text-cyan-500 animate-pulse" />
                            <h3 className="text-2xl font-orbitron font-bold text-white tracking-wider uppercase">
                                {profile.name}
                            </h3>
                        </div>
                        <div className="flex items-center gap-2 text-cyan-400/60 text-xs font-mono tracking-widest uppercase">
                            <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
                            Target Profile Identified
                        </div>
                    </div>
                </div>

                {/* AI Response Block */}
                {profile.ai_response && (
                    <div className="mb-6 group/response">
                        <div className="flex items-center gap-2 mb-2">
                            <ChevronRight className="w-4 h-4 text-cyan-500" />
                            <h4 className="text-cyan-400 font-mono text-xs tracking-widest uppercase">Analysis Overview</h4>
                        </div>
                        <div className="p-4 bg-cyan-950/20 rounded-lg border-l-2 border-cyan-500/50 text-gray-300 font-light leading-relaxed whitespace-pre-wrap text-sm">
                            {profile.ai_response}
                        </div>
                    </div>
                )}

                {/* Description Grid */}
                {profile.description && (
                    <div className="mb-6">
                        <div className="flex items-center gap-2 mb-2">
                            <ChevronRight className="w-4 h-4 text-cyan-500" />
                            <h4 className="text-cyan-400 font-mono text-xs tracking-widest uppercase">Extracted Bio</h4>
                        </div>
                        <p className="text-gray-400 font-light text-sm pl-6">{profile.description}</p>
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 relative">
                    {/* Social Links */}
                    {socialLinks.length > 0 && (
                        <div>
                            <div className="flex items-center gap-2 mb-3">
                                <ChevronRight className="w-4 h-4 text-cyan-500" />
                                <h4 className="text-cyan-400 font-mono text-xs tracking-widest uppercase">Network Nodes</h4>
                            </div>
                            <div className="grid grid-cols-2 gap-2 pl-6">
                                {socialLinks.map(({ icon: Icon, url, label }) => (
                                    <motion.a
                                        key={label}
                                        href={url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-2 p-2.5 rounded-md border border-cyan-900/50 bg-cyan-950/20 hover:bg-cyan-900/40 hover:border-cyan-500/50 transition-all group/link"
                                        whileHover={{ x: 4 }}
                                        whileTap={{ scale: 0.98 }}
                                    >
                                        <Icon className="w-4 h-4 text-cyan-500 group-hover/link:text-cyan-300 transition-colors" />
                                        <span className="text-xs text-gray-300 font-mono tracking-wider">{label}</span>
                                    </motion.a>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Similar Profiles */}
                    {profile.similar_profiles && profile.similar_profiles.length > 0 && (
                        <div>
                            <div className="flex items-center gap-2 mb-3">
                                <ChevronRight className="w-4 h-4 text-cyan-500" />
                                <h4 className="text-cyan-400 font-mono text-xs tracking-widest uppercase flex items-center gap-2">
                                    <Users className="w-3.5 h-3.5" />
                                    Correlated Targets
                                </h4>
                            </div>
                            <div className="flex flex-wrap gap-2 pl-6">
                                {profile.similar_profiles.map((name, index) => (
                                    <span
                                        key={index}
                                        className="px-2.5 py-1 rounded bg-blue-950/30 border border-blue-900/50 text-xs text-blue-300 font-mono tracking-wider"
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
