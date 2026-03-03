'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Clock } from 'lucide-react';

interface SocialGaugeProps {
    score?: number;
    lastActive?: string;
}

function SocialGauge({ score, lastActive }: SocialGaugeProps) {
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
            className={`fixed z-40 right-6 bottom-6 w-56 glass-strong rounded-[1.5rem] border border-white/5 bg-black/40 backdrop-blur-xl flex flex-col overflow-hidden pointer-events-auto group/gauge ${glowClass} transition-shadow duration-1000`}
        >
            {/* Header */}
            <div className="p-3 border-b border-white/10 bg-black/40 flex items-center gap-2 relative overflow-hidden">
                <div className={`absolute inset-0 bg-gradient-to-r ${colorClass} opacity-10`} />
                <Activity className={`w-4 h-4 ${textColorClass} animate-pulse`} />
                <span className={`text-[10px] font-bold font-mono tracking-widest ${textColorClass} uppercase`}>
                    Activity Matrix
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
