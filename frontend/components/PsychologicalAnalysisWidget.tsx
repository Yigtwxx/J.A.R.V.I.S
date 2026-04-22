'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Shield, Target, ChevronDown, ChevronUp, AlertTriangle, Crosshair, Eye } from 'lucide-react';
import { PsychologicalAnalysis } from '@/types/profile';
import { useTranslations } from 'next-intl';

interface Props {
    analysis: PsychologicalAnalysis;
}

const riskColor = (level: string) => {
    switch (level) {
        case 'high': return 'text-red-400 bg-red-900/30 border-red-500/30';
        case 'medium': return 'text-orange-400 bg-orange-900/30 border-orange-500/30';
        default: return 'text-yellow-400 bg-yellow-900/30 border-yellow-500/30';
    }
};

const PsychologicalAnalysisWidget: React.FC<Props> = ({ analysis }) => {
    const t = useTranslations('psychAnalysis');
    const [isExpanded, setIsExpanded] = useState(false);
    const [showVectors, setShowVectors] = useState(false);

    const score = analysis.manipulation_resistance_score;
    const scoreColor = score >= 70 ? 'text-emerald-400' : score >= 40 ? 'text-orange-400' : 'text-red-400';
    const scoreBg = score >= 70 ? 'bg-emerald-500' : score >= 40 ? 'bg-orange-500' : 'bg-red-500';

    return (
        <div className="mt-6 border border-red-900/40 rounded-lg bg-black/40 overflow-hidden glass-3d animate-depth-breathe">
            {/* Header */}
            <div
                className="p-3 flex items-center justify-between cursor-pointer bg-red-900/20 hover:bg-red-900/30 transition-colors"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-2">
                    <Brain size={16} className="text-red-400" />
                    <span className="text-xs font-mono font-bold text-red-300 tracking-wider uppercase">
                        {t('title')}
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                        <Shield size={12} className={scoreColor} />
                        <span className={`text-xs font-mono font-bold ${scoreColor}`}>
                            RESISTANCE: {score}/100
                        </span>
                    </div>
                    {isExpanded ? <ChevronUp size={14} className="text-red-400" /> : <ChevronDown size={14} className="text-red-400" />}
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
                        <div className="p-4 space-y-4">
                            {/* Resistance Score Bar */}
                            <div>
                                <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: `${score}%` }}
                                        transition={{ duration: 1, ease: 'easeOut' }}
                                        className={`h-full rounded-full ${scoreBg}`}
                                    />
                                </div>
                                <div className="flex justify-between mt-1">
                                    <span className="text-[10px] text-red-500/60 font-mono">VULNERABLE</span>
                                    <span className="text-[10px] text-emerald-500/60 font-mono">RESISTANT</span>
                                </div>
                            </div>

                            {/* Psychological Profile */}
                            <div className="bg-red-950/20 border border-red-900/30 rounded-md p-3">
                                <div className="flex items-center gap-1.5 mb-2">
                                    <Eye size={12} className="text-red-400" />
                                    <span className="text-[10px] font-mono text-red-400 uppercase tracking-wider">Profile Assessment</span>
                                </div>
                                <p className="text-xs text-gray-300 leading-relaxed">{analysis.psychological_profile}</p>
                            </div>

                            {/* Strengths & Weaknesses */}
                            <div className="grid grid-cols-2 gap-3">
                                {/* Strengths */}
                                <div className="bg-emerald-950/20 border border-emerald-900/30 rounded-md p-3">
                                    <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-wider">Strengths</span>
                                    <ul className="mt-2 space-y-1.5">
                                        {analysis.strengths.map((s, i) => (
                                            <li key={i} className="text-[11px] text-emerald-200/80 flex items-start gap-1.5">
                                                <span className="text-emerald-500 mt-0.5 shrink-0">+</span>
                                                {s}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                                {/* Weaknesses */}
                                <div className="bg-red-950/20 border border-red-900/30 rounded-md p-3">
                                    <span className="text-[10px] font-mono text-red-400 uppercase tracking-wider">Weaknesses</span>
                                    <ul className="mt-2 space-y-1.5">
                                        {analysis.weaknesses.map((w, i) => (
                                            <li key={i} className="text-[11px] text-red-200/80 flex items-start gap-1.5">
                                                <span className="text-red-500 mt-0.5 shrink-0">-</span>
                                                {w}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>

                            {/* Tactical Recommendations */}
                            <div className="bg-orange-950/20 border border-orange-900/30 rounded-md p-3">
                                <div className="flex items-center gap-1.5 mb-2">
                                    <Crosshair size={12} className="text-orange-400" />
                                    <span className="text-[10px] font-mono text-orange-400 uppercase tracking-wider">
                                        Tactical Recommendations
                                    </span>
                                </div>
                                <ol className="space-y-1.5">
                                    {analysis.tactical_recommendations.map((t, i) => (
                                        <li key={i} className="text-[11px] text-orange-200/80 flex items-start gap-2">
                                            <span className="text-orange-500 font-mono font-bold shrink-0">{i + 1}.</span>
                                            {t}
                                        </li>
                                    ))}
                                </ol>
                            </div>

                            {/* Social Engineering Vectors (expandable) */}
                            {analysis.social_engineering_vectors.length > 0 && (
                                <div>
                                    <button
                                        onClick={(e) => { e.stopPropagation(); setShowVectors(!showVectors); }}
                                        className="flex items-center gap-2 text-[10px] font-mono text-red-400 hover:text-red-300 transition-colors uppercase tracking-wider"
                                    >
                                        <Target size={12} />
                                        Social Engineering Vectors ({analysis.social_engineering_vectors.length})
                                        {showVectors ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                    </button>
                                    <AnimatePresence>
                                        {showVectors && (
                                            <motion.div
                                                initial={{ height: 0, opacity: 0 }}
                                                animate={{ height: 'auto', opacity: 1 }}
                                                exit={{ height: 0, opacity: 0 }}
                                                className="mt-2 space-y-2 overflow-hidden"
                                            >
                                                {analysis.social_engineering_vectors.map((vec, i) => (
                                                    <div key={i} className={`border rounded-md p-2.5 ${riskColor(vec.risk_level)}`}>
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-[11px] font-mono font-bold">{vec.vector}</span>
                                                            <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-current">
                                                                {vec.risk_level}
                                                            </span>
                                                        </div>
                                                        <p className="text-[10px] text-gray-300/80">{vec.approach}</p>
                                                    </div>
                                                ))}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </div>
                            )}

                            {/* Confidence */}
                            <div className="flex items-center justify-end gap-2 pt-1 border-t border-red-900/20">
                                <AlertTriangle size={10} className="text-gray-500" />
                                <span className="text-[9px] text-gray-500 font-mono">
                                    Analysis confidence: {(analysis.confidence_level * 100).toFixed(0)}%
                                </span>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default PsychologicalAnalysisWidget;
