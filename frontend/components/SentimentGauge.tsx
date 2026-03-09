import React from 'react';
import { motion } from 'framer-motion';
import { Activity, BrainCircuit } from 'lucide-react';

interface SentimentData {
    positive: number;
    neutral: number;
    negative: number;
    dominant_emotion: string;
    summary: string;
}

interface SentimentGaugeProps {
    data: SentimentData;
}

export default function SentimentGauge({ data }: SentimentGaugeProps) {
    // Ensuring total is 100 for SVG rendering
    const total = data.positive + data.neutral + data.negative;
    const pos = total > 0 ? (data.positive / total) * 100 : 33;
    const neu = total > 0 ? (data.neutral / total) * 100 : 34;
    const neg = total > 0 ? (data.negative / total) * 100 : 33;

    // SVG Circle Math (Radius 40 -> Circumference ~251.2)
    const circumference = 2 * Math.PI * 40;

    // Calculate offsets for an overlapping segmented gauge
    const posStroke = (pos / 100) * circumference;
    const neuStroke = (neu / 100) * circumference;
    const negStroke = (neg / 100) * circumference;

    // Start angles (using dashoffset trick to stack them along the circle)
    const posStart = 0;
    const neuStart = posStart + (pos / 100) * 360;
    const negStart = neuStart + (neu / 100) * 360;

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="w-full glass-strong rounded-[1.2rem] border border-cyan-500/30 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_15px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden relative group/sentiment"
        >
            {/* Header */}
            <div className="p-3 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center justify-between relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_4s_infinite]" />
                <div className="flex items-center gap-2">
                    <BrainCircuit className="w-4 h-4 text-cyan-400" />
                    <span className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan">Psychological Profile</span>
                </div>
                <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_cyan]" />
            </div>

            <div className="p-4 flex flex-col md:flex-row gap-5 items-center">

                {/* Visual Donut Chart */}
                <div className="relative w-28 h-28 flex items-center justify-center shrink-0">
                    <svg className="w-full h-full transform -rotate-90 drop-shadow-lg" viewBox="0 0 100 100">
                        {/* Background Track */}
                        <circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="transparent"
                            stroke="rgba(6, 182, 212, 0.1)"
                            strokeWidth="8"
                        />

                        {/* Negative (Red) */}
                        <motion.circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="transparent"
                            stroke="#ef4444"
                            strokeWidth="8"
                            strokeDasharray={`${negStroke} ${circumference}`}
                            initial={{ strokeDasharray: `0 ${circumference}` }}
                            animate={{ strokeDasharray: `${negStroke} ${circumference}` }}
                            transition={{ duration: 1.5, delay: 0.2, ease: "easeOut" }}
                            className="drop-shadow-[0_0_8px_rgba(239,68,68,0.5)]"
                            style={{ transformOrigin: "50% 50%", transform: `rotate(${negStart}deg)` }}
                            strokeLinecap="round"
                        />

                        {/* Neutral (Blue/Gray) */}
                        <motion.circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="transparent"
                            stroke="#64748b"
                            strokeWidth="8"
                            strokeDasharray={`${neuStroke} ${circumference}`}
                            initial={{ strokeDasharray: `0 ${circumference}` }}
                            animate={{ strokeDasharray: `${neuStroke} ${circumference}` }}
                            transition={{ duration: 1.5, delay: 0.1, ease: "easeOut" }}
                            className="drop-shadow-[0_0_8px_rgba(100,116,139,0.5)]"
                            style={{ transformOrigin: "50% 50%", transform: `rotate(${neuStart}deg)` }}
                            strokeLinecap="round"
                        />

                        {/* Positive (Green) */}
                        <motion.circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="transparent"
                            stroke="#22c55e"
                            strokeWidth="8"
                            strokeDasharray={`${posStroke} ${circumference}`}
                            initial={{ strokeDasharray: `0 ${circumference}` }}
                            animate={{ strokeDasharray: `${posStroke} ${circumference}` }}
                            transition={{ duration: 1.5, ease: "easeOut" }}
                            className="drop-shadow-[0_0_8px_rgba(34,197,94,0.5)]"
                            style={{ transformOrigin: "50% 50%", transform: `rotate(${posStart}deg)` }}
                            strokeLinecap="round"
                        />
                    </svg>

                    {/* Dominant Emotion Center Text */}
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 1 }}
                            className="text-[10px] font-black font-orbitron tracking-wider text-center translate-y-0.5"
                        >
                            <span className="text-white drop-shadow-[0_0_5px_rgba(255,255,255,0.8)] block max-w-[70px] leading-tight truncate px-1">
                                {data.dominant_emotion}
                            </span>
                        </motion.div>
                    </div>
                </div>

                {/* Metrics Breakdown */}
                <div className="flex-1 w-full flex flex-col justify-center space-y-3 font-mono">
                    <div className="flex items-center justify-between group">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_5px_rgba(34,197,94,0.8)]" />
                            <span className="text-[10px] text-green-300 uppercase tracking-widest">Positive</span>
                        </div>
                        <span className="text-xs font-bold text-white group-hover:text-green-400 transition-colors">{Math.round(pos)}%</span>
                    </div>

                    <div className="flex items-center justify-between group">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-slate-500 shadow-[0_0_5px_rgba(100,116,139,0.8)]" />
                            <span className="text-[10px] text-slate-300 uppercase tracking-widest">Neutral</span>
                        </div>
                        <span className="text-xs font-bold text-white group-hover:text-slate-400 transition-colors">{Math.round(neu)}%</span>
                    </div>

                    <div className="flex items-center justify-between group">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.8)]" />
                            <span className="text-[10px] text-red-300 uppercase tracking-widest">Negative</span>
                        </div>
                        <span className="text-xs font-bold text-white group-hover:text-red-400 transition-colors">{Math.round(neg)}%</span>
                    </div>
                </div>
            </div>

            {/* AI Summary Footer */}
            <div className="px-4 py-2 border-t border-cyan-500/10 bg-black/20">
                <div className="flex items-start gap-2">
                    <Activity className="w-3 h-3 text-cyan-500 mt-1 shrink-0" />
                    <p className="text-[10px] leading-relaxed font-mono text-cyan-100/70 line-clamp-2 italic">
                        "{data.summary}"
                    </p>
                </div>
            </div>

            {/* Hover FX */}
            <div className="absolute inset-0 border-2 border-transparent group-hover/sentiment:border-cyan-400/20 rounded-[1.2rem] transition-all duration-500 pointer-events-none" />
        </motion.div>
    );
}
