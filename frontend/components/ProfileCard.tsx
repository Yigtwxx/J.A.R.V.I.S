'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { motion } from 'framer-motion';
import { SearchResponse } from '@/types/profile';
import { User, Users, ChevronRight, Activity, AlertTriangle, FileText, FileJson, FileSpreadsheet, Download } from 'lucide-react';
import dynamic from 'next/dynamic';
import GlitchText from '@/components/ui/GlitchText';
import { exportPdfFromData, exportJsonFromData, exportCsvFromData } from '@/services/api';
import { showError } from '@/lib/toast';

function extractUsername(url: string): string {
    try {
        const pathname = new URL(url).pathname.replace(/\/+$/, '');
        const segments = pathname.split('/').filter(Boolean);
        return segments.length > 0 ? segments[segments.length - 1] : url;
    } catch {
        return url;
    }
}

// ForceGraph and Map MUST be loaded dynamically to avoid SSR 'window is not defined' error
const NetworkGraph = dynamic(() => import('@/components/NetworkGraph'), { ssr: false });
const SecurityScanWidget = dynamic(() => import('@/components/SecurityScanWidget'), { ssr: false });
const GeoIntMap = dynamic(() => import('@/components/GeoIntMap'), { ssr: false });
const LiveCamerasWidget = dynamic(() => import('@/components/LiveCamerasWidget'), { ssr: false });
const PsychologicalAnalysisWidget = dynamic(() => import('@/components/PsychologicalAnalysisWidget'), { ssr: false });
const PredictiveAnalysisWidget = dynamic(() => import('@/components/PredictiveAnalysisWidget'), { ssr: false });

interface ProfileCardProps {
    profile: SearchResponse;
}

function ProfileCard({ profile }: ProfileCardProps) {
    const t = useTranslations('provenance');
    const tTimeline = useTranslations('timeline');
    const tDisamb = useTranslations('disambiguation');
    const tGov = useTranslations('governance');
    const [exporting, setExporting] = useState<string | null>(null);
    const [showExport, setShowExport] = useState(false);

    const handleExport = async (format: 'pdf' | 'json' | 'csv') => {
        setExporting(format);
        try {
            const exportFn = { pdf: exportPdfFromData, json: exportJsonFromData, csv: exportCsvFromData }[format];
            const blob = await exportFn(profile);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const safeName = (profile.name || 'unknown').replace(/\s+/g, '_');
            const ext = format === 'pdf' ? 'pdf' : format === 'json' ? 'json' : 'csv';
            a.download = `JARVIS_Dossier_${safeName}.${ext}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error(`Export ${format} failed:`, err);
            showError('Export failed. Please try again.');
        } finally {
            setExporting(null);
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            whileHover={{ y: -5 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="w-full relative mt-4 group"
        >
            {/* Tech Corner Accents */}
            <div className="absolute top-0 left-0 w-10 h-10 border-t-2 border-l-2 border-cyan-400 rounded-tl-xl opacity-80 shadow-[0_0_15px_rgba(0,255,255,0.4)]" />
            <div className="absolute bottom-0 right-0 w-10 h-10 border-b-2 border-r-2 border-blue-500 rounded-br-xl opacity-80 shadow-[0_0_15px_rgba(10,102,255,0.4)]" />

            <div className="glass-3d rounded-xl p-8 glow-border overflow-hidden relative border-cyan-400/50 animate-depth-breathe">
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
                                <GlitchText text={profile.name || 'Unknown'} interval={4000} />
                            </h3>
                        </div>
                        <div className="flex items-center gap-2 text-cyan-300 text-[11px] font-bold font-mono tracking-widest uppercase glow-cyan mt-1">
                            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse box-shadow-[0_0_10px_cyan]" />
                            Target Profile Identified
                        </div>
                    </div>

                    {/* Export Buttons */}
                    <div className="ml-auto relative">
                        <button
                            onClick={() => setShowExport(!showExport)}
                            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-cyan-400/10 border border-cyan-400/30 text-cyan-300 text-xs font-mono uppercase tracking-wider hover:bg-cyan-400/20 transition-all"
                        >
                            <Download className="w-4 h-4" />
                            Export
                        </button>
                        {showExport && (
                            <motion.div
                                initial={{ opacity: 0, y: -5 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="absolute right-0 top-full mt-2 z-50 flex flex-col gap-1 p-2 rounded-lg bg-slate-900/95 border border-cyan-400/30 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.15)] min-w-[160px]"
                            >
                                {([
                                    { fmt: 'pdf' as const, icon: FileText, label: 'PDF Dossier', color: 'text-red-400' },
                                    { fmt: 'json' as const, icon: FileJson, label: 'JSON Intel', color: 'text-yellow-400' },
                                    { fmt: 'csv' as const, icon: FileSpreadsheet, label: 'CSV Data', color: 'text-green-400' },
                                ]).map(({ fmt, icon: Icon, label, color }) => (
                                    <button
                                        key={fmt}
                                        onClick={() => { handleExport(fmt); setShowExport(false); }}
                                        disabled={exporting === fmt}
                                        className="flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-mono uppercase tracking-wider text-slate-200 hover:bg-cyan-400/10 transition-all disabled:opacity-50"
                                    >
                                        <Icon className={`w-4 h-4 ${color}`} />
                                        {exporting === fmt ? 'Generating...' : label}
                                    </button>
                                ))}
                            </motion.div>
                        )}
                    </div>
                </div>

                {/* Disambiguation warning — low subject confidence + alternative candidates */}
                {typeof profile.subject_confidence === 'number' && profile.subject_confidence < 0.6 &&
                 profile.alternative_candidates && profile.alternative_candidates.length > 0 && (
                    <div className="mb-6 bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 relative overflow-hidden">
                        <div className="flex items-start gap-3">
                            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                            <div className="space-y-2 flex-1">
                                <h4 className="text-amber-300 font-orbitron font-bold text-xs tracking-[0.1em] uppercase">
                                    {tDisamb('title')}
                                </h4>
                                <p className="text-amber-200/90 text-xs font-mono">
                                    {tDisamb('warning', { count: profile.alternative_candidates.length })}
                                    {` · ${tDisamb('confidence')}: ${Math.round(profile.subject_confidence * 100)}%`}
                                </p>
                                <div className="flex flex-wrap gap-2">
                                    {profile.alternative_candidates.map((c, i) => {
                                        const cand = c as { name?: string; source_url?: string };
                                        return cand.source_url ? (
                                            <a key={i} href={cand.source_url} target="_blank" rel="noopener noreferrer"
                                               className="px-2.5 py-1 rounded-md bg-amber-900/30 border border-amber-500/30 text-[11px] font-mono text-amber-100 hover:bg-amber-800/40 transition-colors">
                                                {cand.name || tDisamb('candidate')}
                                            </a>
                                        ) : (
                                            <span key={i} className="px-2.5 py-1 rounded-md bg-amber-900/30 border border-amber-500/30 text-[11px] font-mono text-amber-100">
                                                {cand.name || tDisamb('candidate')}
                                            </span>
                                        );
                                    })}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Content Area */}
                <div className="flex flex-col gap-10 relative">
                    {/* Bio Section */}
                    {profile.description && (
                        <div className="max-w-3xl">
                            <div className="flex items-center gap-2 mb-3">
                                <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase drop-shadow-md glow-cyan">Extracted Bio</h4>
                            </div>
                            <p className="text-slate-100 font-medium text-[15px] pl-6 border-l-2 border-cyan-500/30 ml-2 leading-relaxed">
                                {profile.description}
                            </p>
                        </div>
                    )}

                    {/* Cross Validation Warnings */}
                    {profile.cross_validation_issues && profile.cross_validation_issues.length > 0 && (
                        <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-5 relative overflow-hidden group/warning">
                            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-orange-500/50 to-transparent" />
                            <div className="flex items-start gap-4 relative z-10">
                                <div className="p-2 bg-orange-500/20 rounded-lg shrink-0 mt-0.5 border border-orange-500/20">
                                    <AlertTriangle className="w-5 h-5 text-orange-400 group-hover/warning:animate-pulse" />
                                </div>
                                <div className="space-y-3 flex-1">
                                    <h4 className="text-orange-400 font-orbitron font-bold text-sm tracking-[0.1em] uppercase drop-shadow-md">
                                        Data Integrity Warning
                                    </h4>
                                    <ul className="space-y-2">
                                        {profile.cross_validation_issues.map((issue, idx) => (
                                            <li key={idx} className="flex gap-2 text-orange-200/90 text-sm leading-relaxed">
                                                <span className="text-orange-500 font-bold mt-0.5">›</span>
                                                {issue}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Correlated Targets */}
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
                                        className="px-3.5 py-1.5 rounded-lg bg-blue-900/40 border border-blue-400/40 text-[13px] text-white font-bold font-mono tracking-widest shadow-[0_0_15px_rgba(10,102,255,0.2)] hover:bg-blue-800/60 transition-colors"
                                    >
                                        {name}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Knowledge Graph / Network Connections */}
                    {(() => {
                        const platformMap: { key: keyof SearchResponse; label: string }[] = [
                            { key: 'github_url',     label: 'GitHub' },
                            { key: 'instagram_url',  label: 'Instagram' },
                            { key: 'twitter_url',    label: 'Twitter/X' },
                            { key: 'linkedin_url',   label: 'LinkedIn' },
                            { key: 'spotify_url',    label: 'Spotify' },
                            { key: 'tiktok_url',     label: 'TikTok' },
                            { key: 'snapchat_url',   label: 'Snapchat' },
                            { key: 'tumblr_url',     label: 'Tumblr' },
                            { key: 'youtube_url',    label: 'YouTube' },
                            { key: 'reddit_url',     label: 'Reddit' },
                            { key: 'facebook_url',   label: 'Facebook' },
                            { key: 'pinterest_url',  label: 'Pinterest' },
                            { key: 'medium_url',     label: 'Medium' },
                            { key: 'threads_url',    label: 'Threads' },
                            { key: 'steam_url',      label: 'Steam' },
                        ];
                        const platformNodes = platformMap.flatMap(({ key, label }) => {
                            const val = profile[key];
                            if (!val || typeof val !== 'string') return [];
                            const urls = val.split(',').map(u => u.trim()).filter(u => {
                                try { return ['http:', 'https:'].includes(new URL(u).protocol); }
                                catch { return false; }
                            });
                            if (urls.length === 0) return [];
                            const activity = profile.platform_activity?.[label.toLowerCase().replace('/x', '')] ?? undefined;
                            return urls.map(url => ({
                                name: urls.length > 1 ? `${label} (${extractUsername(url)})` : label,
                                url,
                                activity,
                            }));
                        });
                        return (
                            <div className="mt-4">
                                <NetworkGraph
                                    targetName={profile.name || 'Unknown'}
                                    connections={profile.network_connections ?? []}
                                    platforms={platformNodes}
                                    relationships={profile.relationships ?? []}
                                />
                            </div>
                        );
                    })()}

                    {/* GEOINT — Geographic Intelligence Map */}
                    <GeoIntMap
                        locationCountry={profile.location_country}
                        locationCity={profile.location_city}
                        companyRecords={profile.company_records}
                        geointData={profile.geoint_data}
                        timezoneAnalysis={profile.timezone_analysis}
                    />

                    {/* Live Visual Intelligence — public webcams + latest public images */}
                    <LiveCamerasWidget
                        place={profile.location_city || profile.location_country}
                        query={profile.name}
                    />

                    {/* Threat Intelligence / Dark Web Monitoring */}
                    <SecurityScanWidget
                        emails={profile.email_addresses}
                        dataBreaches={profile.data_breaches}
                    />

                    {/* Governance disclaimer — shown before inference modules (Faz 4.1) */}
                    {(profile.psychological_analysis || profile.prediction_data) && (
                        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3 flex items-start gap-2.5">
                            <AlertTriangle className="w-4 h-4 text-amber-400/80 shrink-0 mt-0.5" />
                            <div>
                                <span className="text-amber-300/90 font-orbitron font-bold text-[10px] tracking-[0.1em] uppercase block">
                                    {tGov('title')}
                                </span>
                                <span className="text-amber-200/70 text-[11px] font-mono leading-relaxed">
                                    {tGov('note')}
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Psychological Warfare Analysis */}
                    {profile.psychological_analysis && (
                        <PsychologicalAnalysisWidget analysis={profile.psychological_analysis} />
                    )}

                    {/* Predictive Analytics Matrix */}
                    {profile.prediction_data && (
                        <PredictiveAnalysisWidget analysis={profile.prediction_data} />
                    )}

                    {/* Sources / Provenance — public-source citations behind structured claims */}
                    {profile.claims && profile.claims.length > 0 && (
                        <div>
                            <div className="flex items-center gap-2 mb-4">
                                <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase flex items-center gap-2 drop-shadow-md glow-cyan">
                                    <FileText className="w-4 h-4 text-cyan-400" />
                                    {t('title')}
                                </h4>
                            </div>
                            <div className="space-y-2.5 pl-6">
                                {profile.claims.map((claim, idx) => (
                                    <div key={idx} className="bg-black/30 border border-cyan-500/15 rounded-lg p-3">
                                        <div className="flex items-center justify-between gap-2 mb-1.5">
                                            <span className="text-[13px] font-mono font-bold text-white truncate">{claim.value}</span>
                                            <span className="text-[10px] font-mono uppercase text-cyan-500/70 tracking-tighter shrink-0">{claim.field}</span>
                                        </div>
                                        <ul className="space-y-1">
                                            {(claim.citations ?? []).map((c, ci) => (
                                                <li key={ci} className="flex items-center justify-between gap-2">
                                                    <a
                                                        href={c.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-[11px] font-mono text-cyan-400/80 hover:text-cyan-300 underline truncate"
                                                    >
                                                        {c.title || c.url}
                                                    </a>
                                                    <span className="text-[9px] font-mono text-white/50 shrink-0 text-right">
                                                        {c.retrieved_at ? `${t('retrievedAt')} ${c.retrieved_at.slice(0, 10)}` : ''}
                                                        {typeof c.confidence === 'number' ? ` · ${t('confidence')} ${Math.round(c.confidence * 100)}%` : ''}
                                                    </span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Timeline — dated public events with sources (Faz 2.5 / 2.6) */}
                    {profile.timeline && profile.timeline.length > 0 && (
                        <div>
                            <div className="flex items-center gap-2 mb-4">
                                <ChevronRight className="w-5 h-5 text-cyan-400 glow-cyan" />
                                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase flex items-center gap-2 drop-shadow-md glow-cyan">
                                    <Activity className="w-4 h-4 text-cyan-400" />
                                    {tTimeline('title')}
                                </h4>
                            </div>
                            <div className="space-y-2.5 pl-6 border-l border-cyan-500/20 ml-2">
                                {profile.timeline.map((raw, idx) => {
                                    const ev = raw as { date?: string; event?: string; source_url?: string };
                                    return (
                                        <div key={idx} className="bg-black/30 border border-cyan-500/15 rounded-lg p-3">
                                            <div className="flex items-center justify-between gap-2 mb-1">
                                                <span className="text-[13px] font-mono text-white/90">{ev.event}</span>
                                                <span className="text-[10px] font-mono uppercase text-cyan-500/70 tracking-tighter shrink-0">{ev.date ? ev.date.slice(0, 10) : ''}</span>
                                            </div>
                                            {ev.source_url && (
                                                <a
                                                    href={ev.source_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-[11px] font-mono text-cyan-400/80 hover:text-cyan-300 underline truncate"
                                                >
                                                    {tTimeline('source')}
                                                </a>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </motion.div>
    );
}

export default React.memo(ProfileCard);
