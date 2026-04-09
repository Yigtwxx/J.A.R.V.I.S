'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { TrendingUp, TrendingDown, Minus, Activity, ChevronDown, ChevronUp, Clock, BarChart3, Zap } from 'lucide-react';
import { PredictiveAnalysis, PredictionEntry } from '@/types/profile';

interface Props {
    analysis: PredictiveAnalysis;
}

const categoryColor: Record<string, string> = {
    activity: 'text-cyan-400 bg-cyan-900/30 border-cyan-500/30',
    behavioral: 'text-purple-400 bg-purple-900/30 border-purple-500/30',
    security: 'text-red-400 bg-red-900/30 border-red-500/30',
    financial: 'text-emerald-400 bg-emerald-900/30 border-emerald-500/30',
};

const trendIcon = (dir: string) => {
    switch (dir) {
        case 'increasing': return <TrendingUp size={14} className="text-emerald-400" />;
        case 'decreasing': return <TrendingDown size={14} className="text-red-400" />;
        case 'erratic': return <Activity size={14} className="text-orange-400" />;
        default: return <Minus size={14} className="text-gray-400" />;
    }
};

const trendColor = (dir: string) => {
    switch (dir) {
        case 'increasing': return 'text-emerald-400';
        case 'decreasing': return 'text-red-400';
        case 'erratic': return 'text-orange-400';
        default: return 'text-gray-400';
    }
};

const probabilityBar = (p: number) => {
    const pct = Math.round(p * 100);
    const color = pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-cyan-500' : 'bg-gray-500';
    return (
        <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                    className={`h-full rounded-full ${color}`}
                />
            </div>
            <span className="text-[10px] font-mono text-gray-400 w-8 text-right">{pct}%</span>
        </div>
    );
};

const PredictionCard: React.FC<{ entry: PredictionEntry; index: number }> = ({ entry, index }) => {
    const [showEvidence, setShowEvidence] = useState(false);
    const colors = categoryColor[entry.category] || categoryColor.behavioral;

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className={`border rounded-md p-3 ${colors}`}
        >
            <div className="flex items-center justify-between mb-1.5">
                <span className="text-[9px] font-mono uppercase tracking-wider opacity-70">{entry.category}</span>
                <div className="flex items-center gap-1.5">
                    <Clock size={10} className="opacity-60" />
                    <span className="text-[9px] font-mono opacity-60">{entry.timeframe}</span>
                </div>
            </div>
            <p className="text-[11px] text-gray-200 mb-2 leading-relaxed">{entry.prediction}</p>
            {probabilityBar(entry.probability)}

            {entry.supporting_evidence.length > 0 && (
                <div className="mt-2">
                    <button
                        onClick={() => setShowEvidence(!showEvidence)}
                        className="text-[9px] font-mono opacity-50 hover:opacity-80 transition-opacity flex items-center gap-1"
                    >
                        Evidence ({entry.supporting_evidence.length})
                        {showEvidence ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                    </button>
                    <AnimatePresence>
                        {showEvidence && (
                            <motion.ul
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="mt-1 space-y-1 overflow-hidden"
                            >
                                {entry.supporting_evidence.map((e, i) => (
                                    <li key={i} className="text-[10px] text-gray-400 pl-2 border-l border-current/20">
                                        {e}
                                    </li>
                                ))}
                            </motion.ul>
                        )}
                    </AnimatePresence>
                </div>
            )}
        </motion.div>
    );
};

const PredictiveAnalysisWidget: React.FC<Props> = ({ analysis }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    if (!analysis.predictions.length) return null;

    return (
        <div className="mt-6 border border-purple-900/40 rounded-lg bg-black/40 overflow-hidden glass-3d animate-depth-breathe">
            {/* Header */}
            <div
                className="p-3 flex items-center justify-between cursor-pointer bg-purple-900/20 hover:bg-purple-900/30 transition-colors"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-2">
                    <BarChart3 size={16} className="text-purple-400" />
                    <span className="text-xs font-mono font-bold text-purple-300 tracking-wider uppercase">
                        Predictive Matrix
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                        {trendIcon(analysis.trend_direction)}
                        <span className={`text-xs font-mono font-bold ${trendColor(analysis.trend_direction)}`}>
                            {analysis.trend_direction.toUpperCase()}
                        </span>
                    </div>
                    <span className="text-[10px] font-mono text-gray-500">
                        {analysis.predictions.length} forecast{analysis.predictions.length > 1 ? 's' : ''}
                    </span>
                    {isExpanded ? <ChevronUp size={14} className="text-purple-400" /> : <ChevronDown size={14} className="text-purple-400" />}
                </div>
            </div>

            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                        className="overflow-hidden"
                    >
                        <div className="p-4 space-y-3">
                            {/* Activity Pattern */}
                            {analysis.activity_pattern && (
                                <div className="bg-purple-950/20 border border-purple-900/30 rounded-md p-3 flex items-center gap-4 flex-wrap">
                                    <div className="flex items-center gap-1.5">
                                        <Zap size={12} className="text-purple-400" />
                                        <span className="text-[10px] font-mono text-purple-400 uppercase">Frequency:</span>
                                        <span className="text-[11px] text-gray-300">{analysis.activity_pattern.posting_frequency}</span>
                                    </div>
                                    {analysis.activity_pattern.most_active_hours?.length > 0 && (
                                        <div className="flex items-center gap-1.5">
                                            <Clock size={12} className="text-cyan-400" />
                                            <span className="text-[10px] font-mono text-cyan-400 uppercase">Peak:</span>
                                            <span className="text-[11px] text-gray-300">
                                                {analysis.activity_pattern.most_active_hours.map(h => `${h}:00`).join(', ')}
                                            </span>
                                        </div>
                                    )}
                                    {analysis.activity_pattern.most_active_days?.length > 0 && (
                                        <div className="flex items-center gap-1.5">
                                            <Activity size={12} className="text-emerald-400" />
                                            <span className="text-[10px] font-mono text-emerald-400 uppercase">Days:</span>
                                            <span className="text-[11px] text-gray-300">
                                                {analysis.activity_pattern.most_active_days.join(', ')}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Prediction Cards */}
                            <div className="space-y-2">
                                {analysis.predictions.map((pred, i) => (
                                    <PredictionCard key={i} entry={pred} index={i} />
                                ))}
                            </div>

                            {/* Data Sufficiency */}
                            <div className="flex items-center justify-between pt-2 border-t border-purple-900/20">
                                <span className="text-[9px] text-gray-500 font-mono">
                                    Data sufficiency: {(analysis.data_sufficiency * 100).toFixed(0)}%
                                </span>
                                <div className="w-20 h-1 bg-gray-800 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-purple-500 rounded-full"
                                        style={{ width: `${analysis.data_sufficiency * 100}%` }}
                                    />
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default PredictiveAnalysisWidget;
