'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { SearchResponse } from '@/types/profile';
import { Github, Instagram, Twitter, Linkedin, User, Users, ChevronRight, Activity, Music, Video, ExternalLink, MapPin, Thermometer, Cloud, Sun, Wind } from 'lucide-react';

interface ProfileCardProps {
    profile: SearchResponse;
}

export default function ProfileCard({ profile }: ProfileCardProps) {
    const allSocials = [
        { icon: Github, url: profile.github_url, label: 'GitHub', color: 'text-white' },
        { icon: Instagram, url: profile.instagram_url, label: 'Instagram', color: 'text-pink-400' },
        { icon: Twitter, url: profile.twitter_url, label: 'X (Twitter)', color: 'text-sky-400' },
        { icon: Linkedin, url: profile.linkedin_url, label: 'LinkedIn', color: 'text-blue-400' },
        { icon: Music, url: profile.spotify_url, label: 'Spotify', color: 'text-green-400' },
        { icon: Video, url: profile.tiktok_url, label: 'TikTok', color: 'text-rose-400' },
    ];

    const socialLinks = allSocials.flatMap(social => {
        if (!social.url) return [];
        const urls = social.url.split(',').map(u => u.trim()).filter(Boolean);
        return urls.map((url, i) => ({
            ...social,
            url,
            label: urls.length > 1 ? `${social.label} #${i + 1}` : social.label
        }));
    });

    const weather = profile.weather_info;

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


                {/* Content Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-10 relative">

                    {/* Left Column: Bio & Correlated Targets */}
                    <div className="space-y-8 flex flex-col justify-start">
                        {/* Description */}
                        {profile.description && (
                            <div>
                                <div className="flex items-center gap-2 mb-3">
                                    <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                    <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase drop-shadow-md glow-cyan">Extracted Bio</h4>
                                </div>
                                <p className="text-slate-100 font-medium text-[15px] pl-6 border-l-2 border-cyan-500/30 ml-2 leading-relaxed">{profile.description}</p>
                            </div>
                        )}

                        {/* Geographic Context */}
                        {(profile.location_country || weather) && (
                            <div>
                                <div className="flex items-center gap-2 mb-4">
                                    <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                    <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase flex items-center gap-2 drop-shadow-md glow-cyan">
                                        <MapPin className="w-4 h-4 text-cyan-400" />
                                        Geographic Context
                                    </h4>
                                </div>
                                <div className="pl-6 space-y-4">
                                    {profile.location_country && (
                                        <div className="flex items-center gap-3">
                                            <div className="px-3 py-1.5 rounded-lg bg-cyan-900/30 border border-cyan-400/40 text-[13px] text-white font-bold font-mono tracking-widest shadow-[0_0_10px_rgba(0,255,255,0.2)]">
                                                {profile.location_country} {profile.location_city ? `(${profile.location_city})` : ''}
                                            </div>
                                        </div>
                                    )}

                                    {weather && (
                                        <div className="flex flex-wrap gap-3">
                                            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-900/40 border border-blue-400/30 shadow-[0_0_15px_rgba(59,130,246,0.2)]">
                                                <Thermometer className="w-4 h-4 text-blue-400" />
                                                <span className="text-white font-mono font-bold">{weather.temperature}°C</span>
                                            </div>
                                            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-white/10 shadow-[0_0_15px_rgba(255,255,255,0.05)]">
                                                {weather.temperature > 20 ? <Sun className="w-4 h-4 text-yellow-400" /> : <Cloud className="w-4 h-4 text-slate-300" />}
                                                <span className="text-slate-200 font-mono text-[13px] font-bold">{weather.description}</span>
                                            </div>
                                            {weather.windspeed && (
                                                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/40 border border-white/5">
                                                    <Wind className="w-3.5 h-3.5 text-slate-400" />
                                                    <span className="text-slate-400 font-mono text-[11px] font-medium tracking-tighter">{weather.windspeed} km/h</span>
                                                </div>
                                            )}
                                        </div>
                                    )}
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

                    {/* Right Column: Social Footprint */}
                    <div className="space-y-8 flex flex-col justify-start">
                        {socialLinks.length > 0 && (
                            <div>
                                <div className="flex items-center gap-2 mb-4">
                                    <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                    <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase drop-shadow-md glow-cyan">Digital Footprint</h4>
                                </div>
                                <div className="grid grid-cols-1 gap-3 pl-6">
                                    {socialLinks.map((link, index) => (
                                        <a
                                            key={index}
                                            href={link.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center justify-between p-3 rounded-xl bg-slate-900/40 border border-cyan-500/20 hover:border-cyan-400/50 transition-all duration-300 group/link overflow-hidden relative"
                                        >
                                            <div className="flex items-center gap-3 relative z-10">
                                                <div className={`p-2 rounded-lg bg-slate-800/50 border border-white/10 ${link.color}`}>
                                                    <link.icon className="w-4 h-4" />
                                                </div>
                                                <span className="text-slate-200 font-mono text-sm font-bold tracking-wider">{link.label}</span>
                                            </div>
                                            <ExternalLink className="w-4 h-4 text-cyan-400/50 group-hover/link:text-cyan-400 transition-colors relative z-10" />
                                            {/* Hover Glow Effect */}
                                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full group-hover/link:translate-x-full transition-transform duration-700" />
                                        </a>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </motion.div>
    );
}
