import React, { useState } from 'react';
import { Shield, ShieldAlert, AlertTriangle, Key, Mail, MapPin, Phone, User, Calendar } from 'lucide-react';

interface BreachData {
    Name: string;
    Title: string;
    Domain: string;
    BreachDate: string;
    DataClasses: string[];
    IsVerified: boolean;
    TargetEmail: string;
}

interface SecurityScanProps {
    emails?: string[];
    dataBreaches?: BreachData[];
}

const SecurityScanWidget: React.FC<SecurityScanProps> = ({ emails = [], dataBreaches = [] }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    const isSecure = dataBreaches.length === 0;
    const isPending = emails.length === 0 && dataBreaches.length === 0;

    // Icon mapping for different types of leaked data
    const getDataClassIcon = (dataClass: string) => {
        const dc = dataClass.toLowerCase();
        if (dc.includes('email')) return <Mail size={12} className="text-cyan-400" />;
        if (dc.includes('password')) return <Key size={12} className="text-red-400" />;
        if (dc.includes('location') || dc.includes('geographic')) return <MapPin size={12} className="text-orange-400" />;
        if (dc.includes('phone')) return <Phone size={12} className="text-emerald-400" />;
        if (dc.includes('name') || dc.includes('username')) return <User size={12} className="text-blue-400" />;
        if (dc.includes('date')) return <Calendar size={12} className="text-purple-400" />;
        return <AlertTriangle size={12} className="text-yellow-400" />;
    };

    if (isPending) {
        return null; // Don't show if no emails were found to scan
    }

    return (
        <div className={`mt-6 border rounded-lg transition-all duration-500 overflow-hidden ${isSecure ? 'border-cyan-500/30 bg-black/40' : 'border-red-900/50 bg-red-950/20'}`}>

            {/* Header Banner */}
            <div
                className={`p-3 flex items-center justify-between cursor-pointer ${isSecure ? 'bg-cyan-900/20 hover:bg-cyan-900/30' : 'bg-red-900/30 hover:bg-red-900/40'}`}
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
                        <h3 className={`font-mono font-bold tracking-wider text-sm ${isSecure ? 'text-cyan-300' : 'text-red-400'}`}>
                            DEEP WEB THREAT ANALYSIS
                        </h3>
                        <p className="text-xs text-gray-400 font-mono mt-0.5">
                            {emails.length} identifier(s) scanned across Dark Nodes.
                            {!isSecure && <span className="text-red-400 ml-1 ml-1">{dataBreaches.length} critical leaks detected.</span>}
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

            {/* Expandable Content Area */}
            {isExpanded && !isSecure && (
                <div className="p-4 border-t border-red-900/30">
                    <div className="space-y-4">
                        {dataBreaches.map((breach, idx) => (
                            <div key={idx} className="relative p-3 rounded bg-black/60 border border-red-900/40 group hover:border-red-700/60 transition-colors">

                                {/* Cyberpunk accent line */}
                                <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-red-600 to-orange-600 rounded-l"></div>

                                <div className="flex justify-between items-start mb-2 ml-2">
                                    <div>
                                        <h4 className="font-mono text-sm font-bold text-red-100">{breach.Title}</h4>
                                        <p className="text-xs text-red-400/80 font-mono flex items-center gap-2 mt-1">
                                            <Calendar size={10} /> {breach.BreachDate} • {breach.Domain}
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
                                    <div className="text-[10px] text-gray-400 font-mono uppercase mb-2">Compromised Data Nodes:</div>
                                    <div className="flex flex-wrap gap-2">
                                        {breach.DataClasses.map((dc, dcIdx) => (
                                            <span key={dcIdx} className="flex items-center gap-1.5 px-2 py-1 bg-red-950/40 border border-red-900/50 rounded-md text-[11px] text-red-200 font-mono">
                                                {getDataClassIcon(dc)}
                                                {dc}
                                            </span>
                                        ))}
                                    </div>
                                </div>

                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Expanded Secure State */}
            {isExpanded && isSecure && (
                <div className="p-4 border-t border-cyan-900/30 bg-black/40">
                    <div className="flex flex-col items-center justify-center py-6 text-center">
                        <Shield className="text-cyan-500/30 mb-3" size={32} />
                        <p className="text-sm text-cyan-300 font-mono">No intelligence leaks detected in known databases.</p>
                        <p className="text-xs text-gray-500 mt-2 max-w-sm">
                            Cross-referenced {emails.length} identifiers against known public breaches and dark web dumps.
                            The target's digital footprint remains uncompromised.
                        </p>
                        <div className="flex gap-2 mt-4">
                            {emails.map((em, idx) => (
                                <span key={idx} className="text-[10px] font-mono text-cyan-500 bg-cyan-950/50 px-2 py-1 rounded border border-cyan-800">
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
