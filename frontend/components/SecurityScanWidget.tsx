import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Shield, ShieldAlert, AlertTriangle, Key, Mail, MapPin, Phone, User, Calendar, FileText } from 'lucide-react';

// ── Breach (HaveIBeenPwned "breachedaccount" response) ──────────────────────
interface BreachData {
    _type?: undefined;          // absent means it's a breach record
    Name: string;
    Title: string;
    Domain: string;
    BreachDate: string;
    PwnCount?: number;
    DataClasses: string[];
    IsVerified: boolean;
    IsSensitive?: boolean;
    IsSpamList?: boolean;
    IsFabricated?: boolean;
    Description?: string;
    TargetEmail: string;
}

// ── Paste (HaveIBeenPwned "pasteaccount" response) ──────────────────────────
interface PasteData {
    _type: 'paste';
    Source: string;
    Id: string;
    Title: string;
    Date: string;
    EmailCount: number;
    TargetEmail: string;
}

type LeakRecord = BreachData | PasteData;

interface SecurityScanProps {
    emails?: string[];
    dataBreaches?: LeakRecord[];
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const isPaste = (r: LeakRecord): r is PasteData => r._type === 'paste';

const fmt = (n?: number) =>
    n ? n.toLocaleString() : null;

const getDataClassIcon = (dataClass: string) => {
    const dc = dataClass.toLowerCase();
    if (dc.includes('email'))                          return <Mail       size={12} className="text-cyan-400"    />;
    if (dc.includes('password'))                       return <Key        size={12} className="text-red-400"     />;
    if (dc.includes('location') || dc.includes('geo')) return <MapPin     size={12} className="text-orange-400"  />;
    if (dc.includes('phone'))                          return <Phone      size={12} className="text-emerald-400" />;
    if (dc.includes('name') || dc.includes('user'))    return <User       size={12} className="text-blue-400"    />;
    if (dc.includes('date'))                           return <Calendar   size={12} className="text-purple-400"  />;
    return <AlertTriangle size={12} className="text-yellow-400" />;
};

// ── Component ────────────────────────────────────────────────────────────────

const SecurityScanWidget: React.FC<SecurityScanProps> = ({ emails = [], dataBreaches = [] }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    const breaches = dataBreaches.filter(r => !isPaste(r)) as BreachData[];
    const pastes   = dataBreaches.filter(r =>  isPaste(r)) as PasteData[];

    const isSecure  = dataBreaches.length === 0;
    const isPending = emails.length === 0 && dataBreaches.length === 0;

    if (isPending) return null;

    return (
        <div className={`mt-6 border rounded-lg transition-all duration-500 overflow-hidden glass-3d animate-depth-breathe ${
            isSecure ? 'border-cyan-500/30 bg-black/40' : 'border-red-900/50 bg-red-950/20'
        }`}>

            {/* ── Header ─────────────────────────────────────────────────── */}
            <div
                className={`p-3 flex items-center justify-between cursor-pointer ${
                    isSecure ? 'bg-cyan-900/20 hover:bg-cyan-900/30' : 'bg-red-900/30 hover:bg-red-900/40'
                }`}
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-3">
                    {isSecure ? (
                        <div className="p-2 rounded-full bg-cyan-500/20 text-cyan-400 animate-pulse">
                            <Shield size={20} />
                        </div>
                    ) : (
                        <div className="p-2 rounded-full bg-red-500/20 text-red-500 animate-pulse">
                            <ShieldAlert size={20} />
                        </div>
                    )}

                    <div>
                        <h3 className={`font-mono font-bold tracking-wider text-sm ${
                            isSecure ? 'text-cyan-300' : 'text-red-400'
                        }`}>
                            DEEP WEB THREAT ANALYSIS
                        </h3>
                        <p className="text-xs text-gray-400 font-mono mt-0.5">
                            {emails.length} identifier(s) scanned across Dark Nodes.
                            {breaches.length > 0 && (
                                <span className="text-red-400 ml-1">
                                    {breaches.length} breach(es)
                                </span>
                            )}
                            {pastes.length > 0 && (
                                <span className="text-orange-400 ml-1">
                                    + {pastes.length} paste(s) detected.
                                </span>
                            )}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {isSecure ? (
                        <span className="px-2 py-1 text-[10px] font-mono rounded bg-emerald-500/20 border border-emerald-500/30 text-emerald-400">
                            SECURE
                        </span>
                    ) : (
                        <span className="px-2 py-1 text-[10px] font-mono rounded bg-red-500/20 border border-red-500/30 text-red-400 animate-pulse">
                            COMPROMISED
                        </span>
                    )}
                    <span className="text-xs text-gray-500 ml-2">{isExpanded ? '[-]' : '[+]'}</span>
                </div>
            </div>

            {/* ── Expanded: threat records ────────────────────────────────── */}
            {isExpanded && !isSecure && (
                <div className="p-4 border-t border-red-900/30 space-y-6">

                    {/* Breaches */}
                    {breaches.length > 0 && (
                        <div className="space-y-4">
                            <div className="text-[10px] text-red-400/70 font-mono uppercase tracking-widest">
                                Data Breaches — {breaches.length} found
                            </div>
                            {breaches.map((breach, idx) => (
                                <motion.div
                                    key={idx}
                                    whileHover={{ y: -3, scale: 1.01, boxShadow: "0 12px 28px rgba(239,68,68,0.18), 0 4px 8px rgba(0,0,0,0.5)" }}
                                    transition={{ type: "spring", stiffness: 300, damping: 22 }}
                                    className="relative p-3 rounded bg-black/60 border border-red-900/40 hover:border-red-700/60 transition-colors"
                                >
                                    {/* Accent bar */}
                                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-red-600 to-orange-600 rounded-l" />

                                    <div className="flex justify-between items-start mb-2 ml-2">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <h4 className="font-mono text-sm font-bold text-red-100">
                                                    {breach.Title}
                                                </h4>
                                                {breach.IsVerified && (
                                                    <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-400">
                                                        VERIFIED
                                                    </span>
                                                )}
                                                {breach.IsSpamList && (
                                                    <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-yellow-900/40 border border-yellow-800/50 text-yellow-400">
                                                        SPAM LIST
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-xs text-red-400/80 font-mono flex items-center gap-2 mt-1">
                                                <Calendar size={10} />
                                                {breach.BreachDate} • {breach.Domain}
                                                {breach.PwnCount && (
                                                    <span className="text-gray-500">
                                                        • {fmt(breach.PwnCount)} records
                                                    </span>
                                                )}
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-[10px] text-gray-400 font-mono mb-1">Target Identity:</div>
                                            <div className="text-xs font-mono text-cyan-400 bg-cyan-900/20 px-2 py-0.5 rounded border border-cyan-800/50">
                                                {breach.TargetEmail}
                                            </div>
                                        </div>
                                    </div>

                                    <div className="ml-2 mt-3 pt-3 border-t border-red-900/30">
                                        <div className="text-[10px] text-gray-400 font-mono uppercase mb-2">
                                            Compromised Data Nodes:
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            {breach.DataClasses.map((dc, dcIdx) => (
                                                <span
                                                    key={dcIdx}
                                                    className="flex items-center gap-1.5 px-2 py-1 bg-red-950/40 border border-red-900/50 rounded-md text-[11px] text-red-200 font-mono"
                                                >
                                                    {getDataClassIcon(dc)}
                                                    {dc}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    )}

                    {/* Pastes */}
                    {pastes.length > 0 && (
                        <div className="space-y-3">
                            <div className="text-[10px] text-orange-400/70 font-mono uppercase tracking-widest">
                                Paste-Site Exposures — {pastes.length} found
                            </div>
                            {pastes.map((paste, idx) => (
                                <motion.div
                                    key={idx}
                                    whileHover={{ y: -3, scale: 1.01, boxShadow: "0 12px 28px rgba(251,146,60,0.15), 0 4px 8px rgba(0,0,0,0.5)" }}
                                    transition={{ type: "spring", stiffness: 300, damping: 22 }}
                                    className="relative p-3 rounded bg-black/60 border border-orange-900/40 hover:border-orange-700/60 transition-colors"
                                >
                                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-orange-600 to-yellow-600 rounded-l" />

                                    <div className="flex justify-between items-start ml-2">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <FileText size={13} className="text-orange-400" />
                                                <h4 className="font-mono text-sm font-bold text-orange-100">
                                                    {paste.Title}
                                                </h4>
                                            </div>
                                            <p className="text-xs text-orange-400/80 font-mono flex items-center gap-2 mt-1">
                                                <Calendar size={10} />
                                                {paste.Date ? paste.Date.split('T')[0] : 'Unknown date'} • {paste.Source}
                                                {paste.EmailCount > 1 && (
                                                    <span className="text-gray-500">
                                                        • {paste.EmailCount.toLocaleString()} emails in paste
                                                    </span>
                                                )}
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-[10px] text-gray-400 font-mono mb-1">Target Identity:</div>
                                            <div className="text-xs font-mono text-cyan-400 bg-cyan-900/20 px-2 py-0.5 rounded border border-cyan-800/50">
                                                {paste.TargetEmail}
                                            </div>
                                        </div>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* ── Expanded: secure state ──────────────────────────────────── */}
            {isExpanded && isSecure && (
                <div className="p-4 border-t border-cyan-900/30 bg-black/40">
                    <div className="flex flex-col items-center justify-center py-6 text-center">
                        <Shield className="text-cyan-500/30 mb-3" size={32} />
                        <p className="text-sm text-cyan-300 font-mono">
                            No intelligence leaks detected in known databases.
                        </p>
                        <p className="text-xs text-gray-500 mt-2 max-w-sm">
                            Cross-referenced {emails.length} identifier(s) against known public breaches
                            and dark web paste dumps. The target's digital footprint remains uncompromised.
                        </p>
                        <div className="flex flex-wrap gap-2 mt-4 justify-center">
                            {emails.map((em, idx) => (
                                <span
                                    key={idx}
                                    className="text-[10px] font-mono text-cyan-500 bg-cyan-950/50 px-2 py-1 rounded border border-cyan-800"
                                >
                                    {em}
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
};

export default SecurityScanWidget;
