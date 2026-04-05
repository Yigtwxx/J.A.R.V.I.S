'use client';

import React, { useEffect, useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Puzzle, ToggleLeft, ToggleRight, Play, Loader2 } from 'lucide-react';
import { getPlugins, togglePlugin, runPlugin } from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import ScrambleText from '@/components/ui/ScrambleText';

const PluginPanel = () => {
    const plugins = useChatStore(state => state.plugins);
    const setPlugins = useChatStore(state => state.setPlugins);
    const [runningPlugin, setRunningPlugin] = useState<string | null>(null);
    const [runQuery, setRunQuery] = useState('');
    const [runTarget, setRunTarget] = useState<string | null>(null);

    const loadPlugins = useCallback(async () => {
        try {
            const data = await getPlugins();
            setPlugins(data.plugins);
        } catch (e) {
            console.error('Failed to load plugins', e);
        }
    }, [setPlugins]);

    useEffect(() => { loadPlugins(); }, [loadPlugins]);

    const handleToggle = async (name: string) => {
        try {
            const result = await togglePlugin(name);
            setPlugins(plugins.map(p => p.name === name ? { ...p, enabled: result.enabled } : p));
        } catch (e) {
            console.error('Failed to toggle plugin', e);
        }
    };

    const handleRun = async (name: string) => {
        if (!runQuery.trim()) return;
        setRunningPlugin(name);
        try {
            await runPlugin(name, runQuery);
            setRunQuery('');
            setRunTarget(null);
        } catch (e) {
            console.error('Failed to run plugin', e);
        } finally { setRunningPlugin(null); }
    };

    return (
        <div className="flex flex-col h-full">
            <div className="p-4 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2">
                <Puzzle className="w-5 h-5 text-orange-400" />
                <ScrambleText text="Plugins" className="text-xs font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
                {plugins.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-cyan-500/40">
                        <Puzzle className="w-8 h-8 mb-2" />
                        <p className="text-[10px] font-mono tracking-widest uppercase">No Plugins Found</p>
                    </div>
                ) : (
                    <AnimatePresence>
                        {plugins.map(p => (
                            <motion.div key={p.name} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                                className="p-3 rounded-lg border border-cyan-500/20 bg-black/20 hover:bg-cyan-900/20 transition-all"
                            >
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-[12px] text-gray-200 font-medium">{p.name}</span>
                                    <button onClick={() => handleToggle(p.name)} className="transition-colors">
                                        {p.enabled ? (
                                            <ToggleRight className="w-5 h-5 text-green-400" />
                                        ) : (
                                            <ToggleLeft className="w-5 h-5 text-gray-500" />
                                        )}
                                    </button>
                                </div>
                                <p className="text-[10px] text-gray-400 mb-1">{p.description}</p>
                                <div className="flex items-center gap-2 text-[9px] text-cyan-500/50 font-mono">
                                    <span>v{p.version}</span>
                                    <span>by {p.author}</span>
                                </div>

                                {/* Run section */}
                                {p.enabled && (
                                    <div className="mt-2">
                                        {runTarget === p.name ? (
                                            <div className="flex gap-1">
                                                <input value={runQuery} onChange={e => setRunQuery(e.target.value)} placeholder="Query..." className="flex-1 bg-black/40 border border-cyan-500/20 rounded px-2 py-1 text-[10px] text-gray-200 placeholder:text-cyan-500/30" />
                                                <button onClick={() => handleRun(p.name)} disabled={runningPlugin === p.name} className="p-1 text-green-400 hover:text-green-300 disabled:opacity-40">
                                                    {runningPlugin === p.name ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                                                </button>
                                            </div>
                                        ) : (
                                            <button onClick={() => setRunTarget(p.name)} className="text-[9px] text-cyan-500/50 hover:text-cyan-300 font-mono transition-colors">
                                                Run manually...
                                            </button>
                                        )}
                                    </div>
                                )}
                            </motion.div>
                        ))}
                    </AnimatePresence>
                )}
            </div>

            <div className="px-4 py-2 border-t border-cyan-500/20 text-center bg-black/20">
                <span className="text-[9px] text-cyan-500/60 font-mono tracking-widest uppercase">
                    {plugins.filter(p => p.enabled).length}/{plugins.length} enabled
                </span>
            </div>
        </div>
    );
};

export default PluginPanel;
