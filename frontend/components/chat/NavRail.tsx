'use client';

import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { History, Trash2, Clock, Brain, Eye, Puzzle, Terminal, Heart, ChevronLeft } from 'lucide-react';
import { getSearchHistory, deleteHistoryItem } from '@/services/api';
import { useChatStore, SidePanel } from '@/store/chatStore';
import ScrambleText from '@/components/ui/ScrambleText';
import GlitchText from '@/components/ui/GlitchText';
import dynamic from 'next/dynamic';
import { showError } from '@/lib/toast';

const MemoryPanel = dynamic(() => import('@/components/panels/MemoryPanel'), { ssr: false });
const WatchPanel = dynamic(() => import('@/components/panels/WatchPanel'), { ssr: false });
const PluginPanel = dynamic(() => import('@/components/panels/PluginPanel'), { ssr: false });
const SystemPanel = dynamic(() => import('@/components/panels/SystemPanel'), { ssr: false });
const HealthPanel = dynamic(() => import('@/components/panels/HealthPanel'), { ssr: false });

const PANEL_TABS: { id: Exclude<SidePanel, null>; icon: typeof History; label: string }[] = [
    { id: 'history', icon: History, label: 'Logs' },
    { id: 'memory', icon: Brain, label: 'Memory' },
    { id: 'watch', icon: Eye, label: 'Watch' },
    { id: 'plugins', icon: Puzzle, label: 'Plugins' },
    { id: 'system', icon: Terminal, label: 'System' },
    { id: 'health', icon: Heart, label: 'Health' },
];

/* Search history list — preserved from the original HistorySidebar. */
const HistoryContent = () => {
    const history = useChatStore(state => state.history);
    const setHistory = useChatStore(state => state.setHistory);
    const setInput = useChatStore(state => state.setInput);

    const loadHistory = React.useCallback(async () => {
        try {
            const data = await getSearchHistory();
            setHistory(data);
        } catch (error) {
            console.error('Failed to load history', error);
            showError('Failed to load search history.');
        }
    }, [setHistory]);

    useEffect(() => {
        loadHistory();
    }, [loadHistory]);

    const handleDeleteHistory = async (id: number) => {
        try {
            await deleteHistoryItem(id);
            setHistory(prev => prev.filter(item => item.id !== id));
        } catch (error) {
            console.error('Failed to delete history item', error);
            showError('Failed to delete history item.');
        }
    };

    return (
        <div className="flex flex-col h-full">
            <div className="p-4 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden shrink-0">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_5s_infinite]"></div>
                <History className="w-5 h-5 text-cyan-400" />
                <ScrambleText text="Secure Logs" className="text-xs font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
                {history.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-cyan-500/40 opacity-70">
                        <Clock className="w-8 h-8 mb-2" />
                        <p className="text-[10px] font-mono tracking-widest uppercase">No Records</p>
                    </div>
                ) : (
                    <AnimatePresence>
                        {history.map((item) => (
                            <motion.div
                                key={item.id}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.9 }}
                                role="button"
                                tabIndex={0}
                                className="group/hist flex items-center justify-between p-2.5 rounded-lg hover:bg-cyan-900/40 border border-transparent hover:border-cyan-500/30 transition-all cursor-pointer shadow-sm hover:shadow-[0_0_10px_rgba(0,255,255,0.1)]"
                                onClick={() => setInput(item.query_name)}
                                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setInput(item.query_name); } }}
                            >
                                <div className="flex items-center gap-2 overflow-hidden">
                                    <div className="w-1.5 h-1.5 rounded-full bg-cyan-500/50 group-hover/hist:bg-cyan-400 group-hover/hist:shadow-[0_0_5px_rgba(0,255,255,0.8)] transition-all shrink-0"></div>
                                    <span className="text-[13px] text-gray-300 font-medium truncate group-hover/hist:text-white transition-colors">{item.query_name}</span>
                                </div>
                                <button
                                    onClick={(e) => { e.stopPropagation(); handleDeleteHistory(item.id); }}
                                    className="opacity-0 group-hover/hist:opacity-100 p-1.5 text-cyan-700 hover:text-red-400 hover:bg-red-950/30 rounded-md transition-all shrink-0"
                                    title="Delete Log"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                )}
            </div>
            <div className="px-4 py-2 border-t border-cyan-500/20 text-center bg-black/20">
                <span className="text-[9px] text-cyan-500/60 font-mono tracking-widest uppercase flex items-center justify-center gap-1.5"><Clock className="w-3 h-3" /> Logs expire in 7 days</span>
            </div>
        </div>
    );
};

/* NavRail (formerly HistorySidebar): persistent left navigation rail with a
 * sliding panel drawer. Hosts all six feature panels — logic preserved. */
const NavRail = () => {
    const activeSidePanel = useChatStore(state => state.activeSidePanel);
    const setActiveSidePanel = useChatStore(state => state.setActiveSidePanel);

    const renderPanel = () => {
        switch (activeSidePanel) {
            case 'memory': return <MemoryPanel />;
            case 'watch': return <WatchPanel />;
            case 'plugins': return <PluginPanel />;
            case 'system': return <SystemPanel />;
            case 'health': return <HealthPanel />;
            case 'history': return <HistoryContent />;
            default: return null;
        }
    };

    const toggle = (id: Exclude<SidePanel, null>) => {
        setActiveSidePanel(activeSidePanel === id ? null : id);
    };

    return (
        <div className="h-screen flex z-30">
            {/* ── Rail ─────────────────────────────────────────────── */}
            <motion.nav
                initial={{ opacity: 0, x: -40 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.7, ease: 'easeOut' }}
                className="w-[164px] h-full flex flex-col glass-strong border-r border-cyan-500/15 bg-jarvis-darker/60 backdrop-blur-md shrink-0"
            >
                {/* Brand */}
                <div className="flex items-center gap-3 px-3.5 py-5 border-b border-cyan-500/15">
                    <div className="relative w-10 h-10 rounded-xl overflow-hidden border-2 border-cyan-500/60 shadow-[0_0_18px_rgba(0,255,255,0.3)] bg-black/40 flex items-center justify-center shrink-0">
                        <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/20 to-transparent" />
                        <span className="text-lg font-black text-cyan-400 font-orbitron glow-cyan select-none">J</span>
                    </div>
                    <div className="flex flex-col overflow-hidden">
                        <h1 className="text-[13px] font-black tracking-[0.18em] uppercase font-orbitron leading-none">
                            <GlitchText
                                text="J.A.R.V.I.S"
                                interval={6000}
                                className="text-transparent bg-clip-text bg-gradient-to-r from-white via-cyan-100 to-cyan-400"
                            />
                        </h1>
                        <div className="flex items-center gap-1.5 mt-1.5">
                            <span className="relative flex h-1.5 w-1.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-500"></span>
                            </span>
                            <span className="text-[7px] font-bold uppercase tracking-[0.2em] text-cyan-300/70 font-mono">Online</span>
                        </div>
                    </div>
                </div>

                {/* Nav items */}
                <div className="flex-1 overflow-y-auto custom-scrollbar py-3 px-2 space-y-1" role="tablist" aria-label="Side panel navigation">
                    {PANEL_TABS.map(({ id, icon: Icon, label }) => (
                        <button
                            key={id}
                            onClick={() => toggle(id)}
                            title={label}
                            role="tab"
                            aria-selected={activeSidePanel === id}
                            aria-label={label}
                            data-active={activeSidePanel === id}
                            className="nav-rail-item w-full font-orbitron text-[11px] font-bold tracking-[0.12em] uppercase"
                        >
                            <Icon className="w-4 h-4 shrink-0" />
                            <span className="truncate">{label}</span>
                        </button>
                    ))}
                </div>

                {/* Footer status */}
                <div className="px-3 py-3 border-t border-cyan-500/15">
                    <div className="flex items-center gap-1.5 text-[8px] font-mono tracking-widest text-cyan-500/50 uppercase">
                        <span className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse" />
                        Secure Link
                    </div>
                </div>
            </motion.nav>

            {/* ── Drawer ───────────────────────────────────────────── */}
            <AnimatePresence>
                {activeSidePanel && (
                    <motion.div
                        key="drawer"
                        initial={{ width: 0, opacity: 0 }}
                        animate={{ width: 300, opacity: 1 }}
                        exit={{ width: 0, opacity: 0 }}
                        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                        className="h-full overflow-hidden shrink-0"
                    >
                        <div className="w-[300px] h-full flex glass-strong border-r border-cyan-500/20 bg-cyan-950/15 backdrop-blur-md">
                            {/* Panel content (each panel renders its own header) */}
                            <div className="flex-1 min-w-0 overflow-hidden flex flex-col">
                                {renderPanel()}
                            </div>

                            {/* Right-edge collapse strip — never overlaps panel headers */}
                            <button
                                onClick={() => setActiveSidePanel(null)}
                                title="Close panel"
                                aria-label="Close panel"
                                className="w-5 shrink-0 flex items-center justify-center border-l border-cyan-500/10 bg-black/20 text-cyan-500/40 hover:text-cyan-200 hover:bg-cyan-500/10 transition-all"
                            >
                                <ChevronLeft className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default NavRail;
