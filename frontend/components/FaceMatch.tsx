'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FaceMatchReport } from '@/types/profile';
import { ScanFace, CheckCircle2, XCircle, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { strings } from '@/lib/strings';

interface FaceMatchProps {
    report: FaceMatchReport;
}

export default function FaceMatch({ report }: FaceMatchProps) {
    const [expanded, setExpanded] = useState(false);

    // Don't render if no comparisons were made
    if (!report || report.total_comparisons === 0) return null;

    const conf = report.overall_confidence;

    // Determine status color and text based on overall confidence
    let statusColor = 'text-red-400';
    let borderColor = 'border-red-500/30';
    let bgColor = 'bg-red-950/20';
    let glowColor = 'shadow-[0_0_15px_rgba(248,113,113,0.3)]';
    let statusText: string = strings.faceMatch.unverified;
    let StatusIcon = XCircle;

    if (conf >= 80) {
        statusColor = 'text-emerald-400';
        borderColor = 'border-emerald-500/30';
        bgColor = 'bg-emerald-950/20';
        glowColor = 'shadow-[0_0_15px_rgba(52,211,153,0.3)]';
        statusText = strings.faceMatch.highConfidence;
        StatusIcon = CheckCircle2;
    } else if (conf >= 50) {
        statusColor = 'text-amber-400';
        borderColor = 'border-amber-500/30';
        bgColor = 'bg-amber-950/20';
        glowColor = 'shadow-[0_0_15px_rgba(251,191,36,0.3)]';
        statusText = strings.faceMatch.partialMatch;
        StatusIcon = AlertCircle;
    }

    // SVG Circular Progress Gauge
    const radius = 28;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (conf / 100) * circumference;

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className={`w-full mt-4 rounded-xl border ${borderColor} ${bgColor} overflow-hidden backdrop-blur-md relative`}
        >
            {/* Scanning Laser Animation Background */}
            <motion.div
                className="absolute top-0 left-0 w-full h-[2px] bg-cyan-400/50 blur-[2px] z-0"
                animate={{ top: ['0%', '100%', '0%'] }}
                transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
            />

            {/* Header Section */}
            <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setExpanded(!expanded)}
                className={`w-full text-left p-4 flex items-center justify-between cursor-pointer hover:bg-white/5 transition-colors relative z-10 border-b ${expanded ? borderColor : 'border-transparent'}`}
            >
                <div className="flex items-center gap-4">
                    {/* Gauge Icon */}
                    <div className={`relative w-16 h-16 flex items-center justify-center rounded-full bg-slate-900/80 ${glowColor} shrink-0`}>
                        <svg className="w-16 h-16 transform -rotate-90 absolute top-0 left-0">
                            <circle
                                cx="32"
                                cy="32"
                                r={radius}
                                stroke="currentColor"
                                strokeWidth="4"
                                fill="transparent"
                                className="text-slate-700"
                            />
                            <motion.circle
                                cx="32"
                                cy="32"
                                r={radius}
                                stroke="currentColor"
                                strokeWidth="4"
                                fill="transparent"
                                strokeDasharray={circumference}
                                initial={{ strokeDashoffset: circumference }}
                                animate={{ strokeDashoffset }}
                                transition={{ duration: 1.5, ease: "easeOut", delay: 0.5 }}
                                className={statusColor}
                                strokeLinecap="round"
                            />
                        </svg>
                        <div className="absolute inset-0 flex items-center justify-center flex-col">
                            <span className={`text-[15px] font-black font-orbitron ${statusColor}`}>{conf.toFixed(0)}</span>
                            <span className={`text-[8px] font-bold -mt-1 ${statusColor}`}>%</span>
                        </div>
                    </div>

                    {/* Texts */}
                    <div>
                        <div className="flex items-center gap-2 mb-1">
                            <ScanFace className="w-4 h-4 text-cyan-400" />
                            <h3 className="text-sm font-orbitron font-bold text-white tracking-widest uppercase">
                                Identity Verification
                            </h3>
                        </div>
                        <div className={`flex items-center gap-1.5 text-xs font-bold tracking-wide ${statusColor}`}>
                            <StatusIcon className="w-3.5 h-3.5" />
                            {statusText}
                        </div>
                        <p className="text-[10px] text-slate-400 font-mono mt-1">
                            {strings.faceMatch.photosAnalyzed(report.face_detected_count)}
                        </p>
                    </div>
                </div>

                {/* Expand Icon */}
                <div className="p-2 text-slate-400" aria-hidden="true">
                    {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </div>
            </button>

            {/* Expanded Details Section */}
            <AnimatePresence>
                {expanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                        className="overflow-hidden"
                    >
                        <div className="p-4 pt-2 space-y-2 bg-black/20 relative z-10">
                            <div className="text-[10px] font-mono text-cyan-400/70 mb-3 px-1 uppercase tracking-widest border-b border-cyan-900/30 pb-1">
                                {strings.faceMatch.pairwiseTitle}
                            </div>

                            {report.pairs.length === 0 ? (
                                <div className="text-xs text-slate-400 font-mono italic px-2">
                                    {strings.faceMatch.noComparison}
                                </div>
                            ) : (
                                report.pairs.map((pair, idx) => {
                                    const pct = pair.confidence;
                                    const pairColor = pct >= 80 ? 'text-emerald-400' : (pct >= 50 ? 'text-amber-400' : 'text-red-400');
                                    const bgPairColor = pct >= 80 ? 'bg-emerald-400' : (pct >= 50 ? 'bg-amber-400' : 'bg-red-400');

                                    return (
                                        <div key={idx} className="flex items-center justify-between text-xs font-mono px-3 py-2 rounded-lg bg-white/5 border border-white/5">
                                            <div className="flex items-center gap-3">
                                                <span className="text-slate-300 font-semibold">{pair.image_a_label}</span>
                                                <span className="text-slate-600 font-black text-[10px]">↔</span>
                                                <span className="text-slate-300 font-semibold">{pair.image_b_label}</span>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                {/* Mini progress bar */}
                                                <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden hidden sm:block">
                                                    <motion.div
                                                        initial={{ width: 0 }}
                                                        animate={{ width: `${pct}%` }}
                                                        transition={{ duration: 1, delay: 0.1 * idx }}
                                                        className={`h-full ${bgPairColor} rounded-full`}
                                                    />
                                                </div>
                                                <span className={`font-bold w-12 text-right ${pairColor}`}>
                                                    %{pct.toFixed(1)}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}
