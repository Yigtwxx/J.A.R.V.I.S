'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Layers } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';

const TIERS = [
    { label: 'Surface', range: '1-3', color: 'cyan', description: 'Quick scan, best for famous people' },
    { label: 'Medium', range: '4-6', color: 'blue', description: 'Balanced search depth' },
    { label: 'Deep', range: '7-10', color: 'amber', description: 'Multi-agent deep research' },
] as const;

function getTier(depth: number) {
    if (depth <= 3) return 0;
    if (depth <= 6) return 1;
    return 2;
}

const DepthSelector = () => {
    const searchDepth = useChatStore(state => state.searchDepth);
    const setSearchDepth = useChatStore(state => state.setSearchDepth);
    const isLoading = useChatStore(state => state.isLoading);
    const [isExpanded, setIsExpanded] = useState(false);

    const currentTier = getTier(searchDepth);
    const tier = TIERS[currentTier];

    const colorMap = {
        cyan: {
            border: 'border-cyan-500/40',
            bg: 'bg-cyan-900/30',
            text: 'text-cyan-400',
            glow: 'shadow-[0_0_8px_rgba(0,255,255,0.2)]',
            activeBg: 'bg-cyan-500/20',
            activeBorder: 'border-cyan-400/60',
        },
        blue: {
            border: 'border-blue-500/40',
            bg: 'bg-blue-900/30',
            text: 'text-blue-400',
            glow: 'shadow-[0_0_8px_rgba(59,130,246,0.2)]',
            activeBg: 'bg-blue-500/20',
            activeBorder: 'border-blue-400/60',
        },
        amber: {
            border: 'border-amber-500/40',
            bg: 'bg-amber-900/30',
            text: 'text-amber-400',
            glow: 'shadow-[0_0_8px_rgba(245,158,11,0.3)]',
            activeBg: 'bg-amber-500/20',
            activeBorder: 'border-amber-400/60',
        },
    };

    const colors = colorMap[tier.color];

    const handleTierClick = (tierIndex: number) => {
        const defaults = [2, 5, 8];
        setSearchDepth(defaults[tierIndex]);
    };

    return (
        <div className="relative z-20">
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                disabled={isLoading}
                title={`Search Depth: ${searchDepth} (${tier.label})`}
                aria-expanded={isExpanded}
                aria-haspopup="true"
                aria-label="Search depth selector"
                className={`relative rounded-xl h-11 px-3 flex items-center gap-1.5 shrink-0 border transition-all duration-300 disabled:opacity-40 ${colors.border} ${colors.bg} ${colors.text} ${colors.glow} hover:brightness-125`}
            >
                <Layers className="w-4 h-4" />
                <span className="text-[10px] font-mono font-bold tracking-wider">{searchDepth}</span>
                {currentTier === 2 && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                )}
            </button>

            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ opacity: 0, y: 8, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 8, scale: 0.95 }}
                        transition={{ duration: 0.2 }}
                        className="absolute bottom-full mb-3 left-1/2 -translate-x-1/2 w-64 glass-strong rounded-2xl border border-cyan-500/20 p-3 shadow-[0_8px_32px_rgba(0,0,0,0.6)]"
                    >
                        <div className="text-[9px] font-mono text-cyan-500/60 uppercase tracking-widest mb-2 text-center">
                            Search Depth Protocol
                        </div>

                        {/* Tier buttons */}
                        <div className="flex gap-1.5 mb-3">
                            {TIERS.map((t, i) => {
                                const tc = colorMap[t.color];
                                const isActive = currentTier === i;
                                return (
                                    <button
                                        key={t.label}
                                        onClick={() => handleTierClick(i)}
                                        aria-pressed={currentTier === i}
                                        className={`flex-1 py-2 px-1 rounded-lg border text-center transition-all duration-200 ${
                                            isActive
                                                ? `${tc.activeBorder} ${tc.activeBg} ${tc.text} font-bold`
                                                : 'border-white/10 bg-white/[0.03] text-white/40 hover:text-white/60 hover:border-white/20'
                                        }`}
                                    >
                                        <div className="text-[10px] font-mono font-bold">{t.label}</div>
                                        <div className="text-[8px] font-mono opacity-60">{t.range}</div>
                                    </button>
                                );
                            })}
                        </div>

                        {/* Fine-tune slider */}
                        <div className="px-1">
                            <input
                                type="range"
                                min={1}
                                max={10}
                                value={searchDepth}
                                onChange={(e) => setSearchDepth(Number(e.target.value))}
                                className="w-full h-1 rounded-full appearance-none cursor-pointer bg-white/10 accent-cyan-400
                                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                                    [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400
                                    [&::-webkit-slider-thumb]:shadow-[0_0_8px_rgba(0,255,255,0.6)]
                                    [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-cyan-300"
                            />
                            <div className="flex justify-between mt-1">
                                <span className="text-[8px] font-mono text-cyan-500/40">1</span>
                                <span className="text-[8px] font-mono text-cyan-500/40">10</span>
                            </div>
                        </div>

                        {/* Description */}
                        <div className={`mt-2 text-[9px] font-mono text-center ${colors.text} opacity-70`}>
                            {tier.description}
                        </div>

                        {currentTier === 2 && (
                            <div className="mt-2 text-[8px] font-mono text-amber-400/60 text-center border-t border-white/5 pt-2">
                                Deep search takes longer but finds obscure targets
                            </div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Click-outside handler */}
            {isExpanded && (
                <div className="fixed inset-0 z-[-1]" onClick={() => setIsExpanded(false)} />
            )}
        </div>
    );
};

export default DepthSelector;
