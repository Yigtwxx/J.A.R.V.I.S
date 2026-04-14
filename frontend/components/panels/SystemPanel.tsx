'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, Check, X, Clock, AlertTriangle, Play, AppWindow, Globe, Loader2, Activity, Wifi, WifiOff, Database, Cpu } from 'lucide-react';
import { getPendingActions, getActionHistory, approveAction, denyAction, requestCommand, requestAppOpen, requestUrlOpen, getServiceStatus, getHealthLog, ServiceStatusResponse, HealthLogEntry } from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import { SystemAction } from '@/types/profile';
import ScrambleText from '@/components/ui/ScrambleText';
import { showError } from '@/lib/toast';

type ActionTab = 'pending' | 'history' | 'new' | 'status';

const SystemPanel = () => {
    const pendingActions = useChatStore(state => state.pendingActions);
    const setPendingActions = useChatStore(state => state.setPendingActions);

    const [tab, setTab] = useState<ActionTab>('pending');
    const [history, setHistory] = useState<SystemAction[]>([]);
    const [loading, setLoading] = useState(false);

    // Service status
    const [serviceStatus, setServiceStatus] = useState<ServiceStatusResponse | null>(null);
    const [healthLog, setHealthLog] = useState<HealthLogEntry[]>([]);

    // New action form
    const [actionType, setActionType] = useState<'command' | 'app' | 'url'>('command');
    const [actionValue, setActionValue] = useState('');

    const loadPending = useCallback(async () => {
        try {
            const data = await getPendingActions();
            setPendingActions(data.pending_actions);
        } catch (e) {
            console.error('Failed to load pending', e);
            showError('Failed to load pending actions.');
        }
    }, [setPendingActions]);

    const loadHistory = useCallback(async () => {
        try {
            const data = await getActionHistory();
            setHistory(data.history);
        } catch (e) {
            console.error('Failed to load history', e);
            showError('Failed to load action history.');
        }
    }, []);

    const loadServiceStatus = useCallback(async () => {
        try {
            const [status, log] = await Promise.all([getServiceStatus(), getHealthLog()]);
            setServiceStatus(status);
            setHealthLog(log.log);
        } catch (e) {
            console.error('Failed to load service status', e);
            showError('Failed to load service status.');
        }
    }, []);

    useEffect(() => { loadPending(); }, [loadPending]);
    useEffect(() => { if (tab === 'history') loadHistory(); }, [tab, loadHistory]);
    useEffect(() => { if (tab === 'status') loadServiceStatus(); }, [tab, loadServiceStatus]);

    const handleApprove = async (id: string) => {
        setLoading(true);
        try {
            await approveAction(id);
            await loadPending();
        } catch (e) {
            console.error('Approve failed', e);
            showError('Failed to approve action.');
        } finally { setLoading(false); }
    };

    const handleDeny = async (id: string) => {
        try {
            await denyAction(id);
            await loadPending();
        } catch (e) {
            console.error('Deny failed', e);
            showError('Failed to deny action.');
        }
    };

    const handleSubmit = async () => {
        if (!actionValue.trim()) return;
        setLoading(true);
        try {
            if (actionType === 'command') await requestCommand(actionValue);
            else if (actionType === 'app') await requestAppOpen(actionValue);
            else await requestUrlOpen(actionValue);
            setActionValue('');
            setTab('pending');
            await loadPending();
        } catch (e) {
            console.error('Request failed', e);
            showError('Failed to submit request.');
        } finally { setLoading(false); }
    };

    const statusColor = (s: string) => {
        if (s === 'executed') return 'text-green-400';
        if (s === 'denied') return 'text-red-400';
        if (s === 'failed') return 'text-orange-400';
        return 'text-yellow-400';
    };

    return (
        <div className="flex flex-col h-full">
            <div className="p-4 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2">
                <Terminal className="w-5 h-5 text-red-400" />
                <ScrambleText text="System Control" className="text-xs font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
            </div>

            {/* Tabs */}
            <div className="flex border-b border-cyan-500/10">
                {(['pending', 'history', 'new', 'status'] as ActionTab[]).map(t => (
                    <button key={t} onClick={() => setTab(t)}
                        className={`flex-1 py-2 text-[10px] font-mono uppercase tracking-wider transition-colors ${tab === t ? 'text-cyan-300 border-b border-cyan-400' : 'text-cyan-500/40 hover:text-cyan-400/60'}`}
                    >
                        {t === 'pending' ? `Pending (${pendingActions.length})` : t}
                    </button>
                ))}
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
                {tab === 'pending' && (
                    pendingActions.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-cyan-500/40">
                            <Clock className="w-8 h-8 mb-2" />
                            <p className="text-[10px] font-mono tracking-widest uppercase">No Pending Actions</p>
                        </div>
                    ) : (
                        <AnimatePresence>
                            {pendingActions.map(a => (
                                <motion.div key={a.action_id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                                    className="p-3 rounded-lg border border-yellow-500/30 bg-yellow-950/10"
                                >
                                    <div className="flex items-start gap-2 mb-2">
                                        <AlertTriangle className="w-4 h-4 text-yellow-400 shrink-0 mt-0.5" />
                                        <p className="text-[11px] text-gray-200">{a.description}</p>
                                    </div>
                                    <div className="flex gap-2">
                                        <button onClick={() => handleApprove(a.action_id)} disabled={loading}
                                            className="flex-1 py-1.5 bg-green-900/40 hover:bg-green-800/40 border border-green-500/30 rounded-lg text-[10px] text-green-300 font-mono transition-colors flex items-center justify-center gap-1 disabled:opacity-40"
                                        >
                                            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Approve
                                        </button>
                                        <button onClick={() => handleDeny(a.action_id)}
                                            className="flex-1 py-1.5 bg-red-900/40 hover:bg-red-800/40 border border-red-500/30 rounded-lg text-[10px] text-red-300 font-mono transition-colors flex items-center justify-center gap-1"
                                        >
                                            <X className="w-3 h-3" /> Deny
                                        </button>
                                    </div>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    )
                )}

                {tab === 'history' && (
                    history.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-cyan-500/40">
                            <Clock className="w-8 h-8 mb-2" />
                            <p className="text-[10px] font-mono tracking-widest uppercase">No History</p>
                        </div>
                    ) : (
                        history.map(a => (
                            <div key={a.action_id} className="p-2.5 rounded-lg border border-cyan-500/10 bg-black/20">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-[11px] text-gray-300 truncate">{a.description}</span>
                                    <span className={`text-[9px] font-mono uppercase ${statusColor(a.status)}`}>{a.status}</span>
                                </div>
                                {a.result && <p className="text-[9px] text-gray-500 truncate">{a.result}</p>}
                            </div>
                        ))
                    )
                )}

                {tab === 'new' && (
                    <div className="space-y-3">
                        <div className="flex gap-1">
                            {([
                                { type: 'command' as const, icon: Terminal, label: 'CMD' },
                                { type: 'app' as const, icon: AppWindow, label: 'APP' },
                                { type: 'url' as const, icon: Globe, label: 'URL' },
                            ]).map(({ type, icon: Icon, label }) => (
                                <button key={type} onClick={() => setActionType(type)}
                                    className={`flex-1 py-2 rounded-lg text-[10px] font-mono flex items-center justify-center gap-1 border transition-colors ${actionType === type ? 'border-cyan-500/40 bg-cyan-900/30 text-cyan-300' : 'border-cyan-500/10 text-cyan-500/40 hover:text-cyan-400/60'}`}
                                >
                                    <Icon className="w-3 h-3" /> {label}
                                </button>
                            ))}
                        </div>
                        <input value={actionValue} onChange={e => setActionValue(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                            placeholder={actionType === 'command' ? 'Shell command...' : actionType === 'app' ? 'App name...' : 'URL...'}
                            className="w-full bg-black/40 border border-cyan-500/20 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder:text-cyan-500/30 focus:outline-none focus:border-cyan-400/50"
                        />
                        <button onClick={handleSubmit} disabled={loading || !actionValue.trim()}
                            className="w-full py-2 bg-cyan-900/60 hover:bg-cyan-800/60 border border-cyan-500/30 rounded-lg text-xs text-cyan-300 font-mono transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                        >
                            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                            Request Execution
                        </button>
                        <p className="text-[9px] text-yellow-500/50 text-center font-mono">Requires manual approval before execution</p>
                    </div>
                )}

                {tab === 'status' && (
                    <div className="space-y-3">
                        {/* Service Indicators */}
                        {serviceStatus ? (
                            <>
                                <div className="space-y-1.5">
                                    {Object.entries(serviceStatus.services).map(([name, info]) => {
                                        const isHealthy = info.status === 'healthy';
                                        const Icon = name === 'ollama' ? Cpu : name === 'database' ? Database : name === 'chromadb' ? Database : Activity;
                                        return (
                                            <div key={name} className={`flex items-center justify-between p-2 rounded-lg border ${isHealthy ? 'border-emerald-500/20 bg-emerald-950/10' : 'border-red-500/20 bg-red-950/10'}`}>
                                                <div className="flex items-center gap-2">
                                                    {isHealthy ? <Wifi size={12} className="text-emerald-400" /> : <WifiOff size={12} className="text-red-400" />}
                                                    <Icon size={12} className={isHealthy ? 'text-emerald-400' : 'text-red-400'} />
                                                    <span className="text-[10px] font-mono text-gray-300 uppercase">{name}</span>
                                                </div>
                                                <span className={`text-[9px] font-mono uppercase ${isHealthy ? 'text-emerald-400' : 'text-red-400'}`}>
                                                    {info.status}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>

                                {/* Uptime & Monitoring */}
                                <div className="flex items-center justify-between text-[9px] font-mono text-gray-500">
                                    <span>Uptime: {Math.floor(serviceStatus.uptime_seconds / 60)}m</span>
                                    <span className={serviceStatus.is_monitoring ? 'text-emerald-500' : 'text-red-500'}>
                                        {serviceStatus.is_monitoring ? 'MONITORING' : 'OFFLINE'}
                                    </span>
                                </div>

                                {/* Recovery Attempts */}
                                {Object.entries(serviceStatus.recovery_attempts).some(([, v]) => v > 0) && (
                                    <div className="bg-orange-950/20 border border-orange-900/30 rounded p-2">
                                        <span className="text-[9px] font-mono text-orange-400 uppercase">Recovery Attempts</span>
                                        {Object.entries(serviceStatus.recovery_attempts).filter(([, v]) => v > 0).map(([svc, count]) => (
                                            <div key={svc} className="flex justify-between text-[10px] text-orange-300/70 mt-1">
                                                <span>{svc}</span>
                                                <span>{count}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Health Log */}
                                {healthLog.length > 0 && (
                                    <div className="space-y-1">
                                        <span className="text-[9px] font-mono text-gray-500 uppercase">Recent Events</span>
                                        {healthLog.slice(0, 10).map((entry, i) => (
                                            <div key={i} className="text-[9px] font-mono text-gray-500 flex gap-2">
                                                <span className={entry.type === 'recovered' ? 'text-emerald-500' : entry.type === 'failed' ? 'text-red-500' : entry.type === 'warning' ? 'text-orange-500' : 'text-gray-500'}>
                                                    [{entry.service}]
                                                </span>
                                                <span className="truncate">{entry.message}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-cyan-500/40">
                                <Loader2 className="w-6 h-6 animate-spin mb-2" />
                                <p className="text-[10px] font-mono">Loading service status...</p>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default SystemPanel;
