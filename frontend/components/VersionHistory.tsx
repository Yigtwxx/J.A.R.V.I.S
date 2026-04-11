'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ChangeReport } from '@/types/profile';
import { GitCompare, ArrowRight, Clock, ChevronRight, TrendingUp } from 'lucide-react';
import { strings } from '@/lib/strings';

interface VersionHistoryProps {
    report: ChangeReport;
}

function VersionHistory({ report }: VersionHistoryProps) {
    if (!report || report.snapshot_count < 2) return null;

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return '—';
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    const truncateValue = (val: string | null, max = 120) => {
        if (!val) return '—';
        return val.length > max ? val.slice(0, max) + '…' : val;
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2, ease: 'easeOut' }}
            className="w-full relative mt-4"
        >
            {/* Tech Corner Accents */}
            <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-emerald-400 rounded-tl-xl opacity-80 shadow-[0_0_12px_rgba(52,211,153,0.4)]" />
            <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-emerald-500 rounded-br-xl opacity-80 shadow-[0_0_12px_rgba(16,185,129,0.4)]" />

            <div className="glass-strong rounded-xl p-6 glow-border overflow-hidden relative border-emerald-400/30">
                {/* Subtle Background Element */}
                <div className="absolute -top-24 -right-24 w-48 h-48 bg-emerald-400/10 rounded-full blur-[60px] pointer-events-none" />

                {/* Header */}
                <div className="flex items-center gap-4 mb-5 border-b border-emerald-400/30 pb-4 relative">
                    <div className="relative">
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-400/20 to-teal-600/20 border border-emerald-400/50 flex items-center justify-center relative z-10 backdrop-blur-md shadow-[0_0_15px_rgba(52,211,153,0.3)]">
                            <GitCompare className="w-6 h-6 text-emerald-300 glow-white" />
                        </div>
                        <div className="absolute inset-0 bg-emerald-400/25 blur-lg rounded-xl" />
                    </div>
                    <div>
                        <div className="flex items-center gap-2 mb-0.5">
                            <TrendingUp className="w-4 h-4 text-emerald-400 animate-pulse" />
                            <h3 className="text-lg font-orbitron font-black text-white tracking-widest uppercase drop-shadow-lg">
                                {strings.versionHistory.changeReport}
                            </h3>
                        </div>
                        <div className="flex items-center gap-2 text-emerald-300/80 text-[10px] font-bold font-mono tracking-widest uppercase">
                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                            {strings.versionHistory.scanRecords(report.snapshot_count)} • {strings.versionHistory.versionHistory}
                        </div>
                    </div>
                </div>

                {/* Timestamps */}
                <div className="flex items-center gap-3 mb-5 text-xs font-mono">
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-600/40">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <span className="text-slate-300">{formatDate(report.previous_captured_at)}</span>
                    </div>
                    <ArrowRight className="w-4 h-4 text-emerald-400" />
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-500/30">
                        <Clock className="w-3 h-3 text-emerald-400" />
                        <span className="text-emerald-200">{formatDate(report.current_captured_at)}</span>
                    </div>
                </div>

                {/* Changes List */}
                {report.has_changes && report.changes.length > 0 ? (
                    <div className="space-y-3">
                        {report.changes.map((change, idx) => (
                            <motion.div
                                key={`${change.field}-${idx}`}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.1 + idx * 0.08 }}
                                className="rounded-lg border border-amber-500/20 bg-amber-950/10 overflow-hidden"
                            >
                                {/* Field Label */}
                                <div className="flex items-center gap-2 px-4 py-2 bg-amber-900/20 border-b border-amber-500/15">
                                    <ChevronRight className="w-3.5 h-3.5 text-amber-400" />
                                    <span className="text-amber-300 font-orbitron font-bold text-[11px] tracking-[0.12em] uppercase">
                                        {change.field_label}
                                    </span>
                                </div>

                                {/* Old → New Values */}
                                <div className="px-4 py-3 space-y-2">
                                    {/* Old value */}
                                    <div className="flex items-start gap-2">
                                        <span className="text-red-400 font-bold text-xs mt-0.5 shrink-0 w-4 text-center">−</span>
                                        <span className="text-red-300/80 text-sm font-mono leading-relaxed line-through decoration-red-500/30">
                                            {truncateValue(change.old_value)}
                                        </span>
                                    </div>
                                    {/* New value */}
                                    <div className="flex items-start gap-2">
                                        <span className="text-green-400 font-bold text-xs mt-0.5 shrink-0 w-4 text-center">+</span>
                                        <span className="text-green-300 text-sm font-mono leading-relaxed">
                                            {truncateValue(change.new_value)}
                                        </span>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-4">
                        <p className="text-emerald-400/60 text-sm font-mono tracking-wider">
                            {strings.versionHistory.noChanges}
                        </p>
                    </div>
                )}
            </div>
        </motion.div>
    );
}

export default React.memo(VersionHistory);
