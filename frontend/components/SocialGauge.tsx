'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Clock } from 'lucide-react';
import type { ScoreBreakdown } from '@/types/profile';

interface SocialGaugeProps {
    score?: number;
    lastActive?: string;
    breakdown?: ScoreBreakdown;
    platformActivity?: Record<string, number>;
}

const PLATFORM_COLORS: Record<string, { color: string; label: string }> = {
    github: { color: 'bg-gray-400', label: 'GitHub' },
    instagram: { color: 'bg-pink-500', label: 'Instagram' },
    twitter: { color: 'bg-slate-400', label: 'Twitter' },
    linkedin: { color: 'bg-blue-500', label: 'LinkedIn' },
    spotify: { color: 'bg-green-500', label: 'Spotify' },
    tiktok: { color: 'bg-rose-500', label: 'TikTok' },
    snapchat: { color: 'bg-yellow-400', label: 'Snapchat' },
    tumblr: { color: 'bg-indigo-500', label: 'Tumblr' },
    tinder: { color: 'bg-orange-500', label: 'Tinder' },
    bumble: { color: 'bg-amber-400', label: 'Bumble' },
};

const DIMENSION_META: { key: keyof ScoreBreakdown; label: string; color: string }[] = [
    { key: 'platform_presence', label: 'Platform', color: 'bg-violet-500' },
    { key: 'follower_impact', label: 'Followers', color: 'bg-cyan-400' },
    { key: 'activity_intensity', label: 'Activity', color: 'bg-emerald-400' },
    { key: 'web_visibility', label: 'Web', color: 'bg-amber-400' },
    { key: 'digital_diversity', label: 'Diversity', color: 'bg-rose-400' },
];

function SocialGauge({ score, lastActive, breakdown, platformActivity }: SocialGaugeProps) {
    const [animatedScore, setAnimatedScore] = useState(0);

    // Provide default values if missing
    const finalScore = typeof score === 'number' ? Math.max(0, Math.min(100, score)) : 0;
    const finalLastActive = lastActive || 'No data';

    useEffect(() => {
        // Animate score from 0 to final score
        const duration = 1500; // 1.5 seconds
        const steps = 60;
        const stepTime = Math.abs(Math.floor(duration / steps));

        let current = 0;
        const timer = setInterval(() => {
            current += finalScore / steps;
            if (current >= finalScore) {
                setAnimatedScore(finalScore);
                clearInterval(timer);
            } else {
                setAnimatedScore(current);
            }
        }, stepTime);

        return () => clearInterval(timer);
    }, [finalScore]);

    // Determine color based on score
    let colorClass = 'from-red-500 to-rose-600';
    let textColorClass = 'text-red-400';
    let glowClass = 'shadow-[0_0_15px_rgba(244,63,94,0.5)]';
    let ringColor = 'stroke-red-500';

    if (finalScore >= 75) {
        colorClass = 'from-cyan-400 to-blue-500';
        textColorClass = 'text-cyan-400';
        glowClass = 'shadow-[0_0_15px_rgba(34,211,238,0.5)]';
        ringColor = 'stroke-cyan-400';
    } else if (finalScore >= 40) {
        colorClass = 'from-amber-400 to-orange-500';
        textColorClass = 'text-amber-400';
        glowClass = 'shadow-[0_0_15px_rgba(251,191,36,0.5)]';
        ringColor = 'stroke-amber-400';
    }

    // Circular progress math
    const radius = 35;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (animatedScore / 100) * circumference;

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className={`fixed z-40 right-[17rem] bottom-6 w-56 glass-strong rounded-[1.5rem] border border-white/5 bg-black/40 backdrop-blur-xl flex flex-col overflow-hidden pointer-events-auto group/gauge ${glowClass} transition-shadow duration-1000`}
        >
            {/* Header */}
            <div className="p-3 border-b border-white/10 bg-black/40 flex items-center gap-2 relative overflow-hidden">
                <div className={`absolute inset-0 bg-gradient-to-r ${colorClass} opacity-10`} />
                <Activity className={`w-4 h-4 ${textColorClass} animate-pulse`} />
                <span className={`text-[10px] font-bold font-mono tracking-widest ${textColorClass} uppercase`}>
                    Digital Impact
                </span>
            </div>

            <div className="p-4 flex flex-col items-center justify-center relative">
                {/* Background Grid Pattern */}
                <div className="absolute inset-0 opacity-[0.03] bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:8px_8px]" />

                {/* Gauge Container */}
                <div className="relative w-28 h-28 flex items-center justify-center mb-3">
                    {/* Background Ring */}
                    <svg className="w-full h-full transform -rotate-90">
                        <circle
                            cx="56"
                            cy="56"
                            r={radius}
                            className="stroke-gray-800"
                            strokeWidth="8"
                            fill="transparent"
                        />
                        {/* Interactive Foreground Ring */}
                        <circle
                            cx="56"
                            cy="56"
                            r={radius}
                            className={`${ringColor} transition-all duration-300 ease-out`}
                            strokeWidth="8"
                            fill="transparent"
                            strokeDasharray={circumference}
                            strokeDashoffset={strokeDashoffset}
                            strokeLinecap="round"
                            style={{ filter: `drop-shadow(0 0 4px var(--tw-shadow-color))` }}
                        />
                    </svg>

                    {/* Center Content */}
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className={`text-2xl font-black font-orbitron ${textColorClass} drop-shadow-md`}>
                            {Math.round(animatedScore)}
                        </span>
                        <span className="text-[8px] text-gray-500 font-mono uppercase tracking-widest mt-0.5">
                            Score
                        </span>
                    </div>

                    {/* Ping Animation Ring inside */}
                    <div className={`absolute inset-4 rounded-full border border-dashed ${ringColor} opacity-20 animate-[spin_10s_linear_infinite]`} />
                </div>

                {/* Breakdown Mini Bars */}
                {breakdown && (
                    <div className="w-full space-y-1.5 mb-3 z-10">
                        {DIMENSION_META.map(({ key, label, color }) => {
                            const value = breakdown[key] ?? 0;
                            const pct = Math.round(value * 100);
                            return (
                                <div key={key} className="flex items-center gap-2">
                                    <span className="text-[8px] text-gray-500 font-mono w-[52px] text-right truncate uppercase tracking-wider">
                                        {label}
                                    </span>
                                    <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                                        <motion.div
                                            className={`h-full ${color} rounded-full`}
                                            initial={{ width: 0 }}
                                            animate={{ width: `${pct}%` }}
                                            transition={{ duration: 1.2, ease: 'easeOut', delay: 0.3 }}
                                        />
                                    </div>
                                    <span className="text-[8px] text-gray-400 font-mono w-[26px] text-right">
                                        {pct}%
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Per-Platform Activity */}
                {platformActivity && Object.keys(platformActivity).length > 0 && (
                    <div className="w-full space-y-1.5 mb-3 z-10">
                        <div className="flex items-center gap-1 mb-1">
                            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />
                            <span className="text-[7px] text-gray-500 font-mono uppercase tracking-widest">Platform Activity</span>
                        </div>
                        {Object.entries(platformActivity).map(([platform, pct]) => {
                            const meta = PLATFORM_COLORS[platform] || { color: 'bg-gray-500', label: platform };
                            return (
                                <div key={platform} className="flex items-center gap-2">
                                    <span className="text-[8px] text-gray-500 font-mono w-[52px] text-right truncate uppercase tracking-wider">
                                        {meta.label}
                                    </span>
                                    <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                                        <motion.div
                                            className={`h-full ${meta.color} rounded-full`}
                                            initial={{ width: 0 }}
                                            animate={{ width: `${pct}%` }}
                                            transition={{ duration: 1.2, ease: 'easeOut', delay: 0.5 }}
                                        />
                                    </div>
                                    <span className="text-[8px] text-gray-400 font-mono w-[26px] text-right">
                                        {pct}%
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                )}


                {/* Activity Insight */}
                <div className="w-full space-y-2 mt-1 z-10">
                    <div className="flex items-center gap-2 bg-white/5 p-2 rounded-lg border border-white/5 backdrop-blur-sm">
                        <Clock className={`w-3.5 h-3.5 ${textColorClass} shrink-0`} />
                        <div className="flex flex-col overflow-hidden">
                            <span className="text-[8px] font-mono text-gray-500 uppercase tracking-wider mb-0.5">
                                Last Detected Node
                            </span>
                            <span className={`text-[10px] font-bold font-mono truncate ${textColorClass}`}>
                                {finalLastActive}
                            </span>
                        </div>
                    </div>

                    {/* Status Bar */}
                    <div className="h-1 w-full bg-gray-900 rounded-full overflow-hidden mt-2">
                        <motion.div
                            className={`h-full bg-gradient-to-r ${colorClass}`}
                            initial={{ width: 0 }}
                            animate={{ width: `${finalScore}%` }}
                            transition={{ duration: 1.5, ease: "easeOut" }}
                        />
                    </div>
                </div>

                {/* Hover Highlights */}
                <div className="absolute inset-0 border-2 border-transparent group-hover/gauge:border-white/10 rounded-2xl transition-colors duration-500 pointer-events-none" />
            </div>
        </motion.div>
    );
}

export default React.memo(SocialGauge);
