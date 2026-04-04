'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Eye, EyeOff, Plus, StopCircle, Activity, Clock, X } from 'lucide-react';
import { getActiveWatches, startWatch, stopWatch, stopAllWatches } from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import ScrambleText from '@/components/ui/ScrambleText';

const WatchPanel = () => {
    const activeWatches = useChatStore(state => state.activeWatches);
    const setActiveWatches = useChatStore(state => state.setActiveWatches);

    const [showAdd, setShowAdd] = useState(false);
    const [query, setQuery] = useState('');
    const [interval, setInterval_] = useState(60);
    const [loading, setLoading] = useState(false);

    const loadWatches = useCallback(async () => {
        try {
            const data = await getActiveWatches();
            setActiveWatches(data.watches);
        } catch (e) {
            console.error('Failed to load watches', e);
        }
    }, [setActiveWatches]);

    useEffect(() => { loadWatches(); }, [loadWatches]);

    const handleStart = async () => {
        if (!query.trim()) return;
        setLoading(true);
        try {
            await startWatch(query.trim(), interval);
            setQuery('');
            setShowAdd(false);
            await loadWatches();
        } catch (e) {
            console.error('Failed to start watch', e);
        } finally { setLoading(false); }
    };

    const handleStop = async (target: string) => {
        try {
            await stopWatch(target);
            await loadWatches();
        } catch (e) {
            console.error('Failed to stop watch', e);
        }
    };

    const handleStopAll = async () => {
        try {
            await stopAllWatches();
            setActiveWatches([]);
        } catch (e) {
            console.error('Failed to stop all', e);
        }
    };

    return (
        <div className="flex flex-col h-full">
            <div className="p-4 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Eye className="w-5 h-5 text-green-400" />
                    <ScrambleText text="Watch Mode" className="text-xs font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
                </div>
                {activeWatches.length > 0 && (
                    <button onClick={handleStopAll} className="text-[9px] text-red-400/60 hover:text-red-400 font-mono uppercase tracking-wider transition-colors">
                        Stop All
                    </button>
                )}
            </div>

            {/* Add Watch */}
            <div className="p-3 border-b border-cyan-500/10 flex gap-2">
                <button onClick={() => setShowAdd(!showAdd)} className="p-1.5 text-cyan-500 hover:text-green-400">
                    {showAdd ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                </button>
            </div>

            <AnimatePresence>
                {showAdd && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-b border-cyan-500/10">
                        <div className="p-3 space-y-2">
                            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Target name or name/username" className="w-full bg-black/40 border border-cyan-500/20 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder:text-cyan-500/30 focus:outline-none focus:border-cyan-400/50" />
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] text-cyan-500/60">Interval: {interval} min</span>
                                <input type="range" min={5} max={1440} step={5} value={interval} onChange={e => setInterval_(+e.target.value)} className="w-28 accent-cyan-500" />
                            </div>
                            <button onClick={handleStart} disabled={loading || !query.trim()} className="w-full py-1.5 bg-green-900/40 hover:bg-green-800/40 border border-green-500/30 rounded-lg text-xs text-green-300 font-mono transition-colors disabled:opacity-40">
                                {loading ? 'Starting...' : 'Start Watch'}
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Watch List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
                {activeWatches.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-cyan-500/40">
                        <EyeOff className="w-8 h-8 mb-2" />
                        <p className="text-[10px] font-mono tracking-widest uppercase">No Active Watches</p>
                    </div>
                ) : (
                    <AnimatePresence>
                        {activeWatches.map(w => (
                            <motion.div key={w.query} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9 }}
                                className="group p-3 rounded-lg border border-cyan-500/20 bg-black/20 hover:bg-cyan-900/20 transition-all"
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <div className={`w-2 h-2 rounded-full ${w.is_active ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)] animate-pulse' : 'bg-gray-500'}`} />
                                        <span className="text-[12px] text-gray-200 font-medium truncate">{w.query}</span>
                                    </div>
                                    <button onClick={() => handleStop(w.query)} className="opacity-0 group-hover:opacity-100 p-1 text-cyan-700 hover:text-red-400 transition-all">
                                        <StopCircle className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                                <div className="flex items-center gap-3 text-[9px] text-cyan-500/50 font-mono">
                                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{w.interval_minutes}m</span>
                                    <span className="flex items-center gap-1"><Activity className="w-3 h-3" />{w.changes_detected} changes</span>
                                </div>
                                {w.last_checked && (
                                    <p className="text-[9px] text-gray-500 mt-1">Last: {new Date(w.last_checked).toLocaleTimeString()}</p>
                                )}
                            </motion.div>
                        ))}
                    </AnimatePresence>
                )}
            </div>

            <div className="px-4 py-2 border-t border-cyan-500/20 text-center bg-black/20">
                <span className="text-[9px] text-cyan-500/60 font-mono tracking-widest uppercase flex items-center justify-center gap-1.5">
                    <Activity className="w-3 h-3" /> {activeWatches.length} active surveillance{activeWatches.length !== 1 ? 's' : ''}
                </span>
            </div>
        </div>
    );
};

export default WatchPanel;
