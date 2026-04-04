'use client';

import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { History, Trash2, Clock, Brain, Eye, Puzzle, Terminal } from 'lucide-react';
import { getSearchHistory, deleteHistoryItem } from '@/services/api';
import { useChatStore, SidePanel } from '@/store/chatStore';
import ScrambleText from '@/components/ui/ScrambleText';
import dynamic from 'next/dynamic';

const MemoryPanel = dynamic(() => import('@/components/panels/MemoryPanel'), { ssr: false });
const WatchPanel = dynamic(() => import('@/components/panels/WatchPanel'), { ssr: false });
const PluginPanel = dynamic(() => import('@/components/panels/PluginPanel'), { ssr: false });
const SystemPanel = dynamic(() => import('@/components/panels/SystemPanel'), { ssr: false });

const PANEL_TABS: { id: SidePanel; icon: typeof History; label: string }[] = [
    { id: 'history', icon: History, label: 'Logs' },
    { id: 'memory', icon: Brain, label: 'Memory' },
    { id: 'watch', icon: Eye, label: 'Watch' },
    { id: 'plugins', icon: Puzzle, label: 'Plugins' },
    { id: 'system', icon: Terminal, label: 'System' },
];

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
        }
    };

    return (
        <div className="flex flex-col h-full">
            <div className="p-4 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden">
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
                                className="group/hist flex items-center justify-between p-2.5 rounded-lg hover:bg-cyan-900/40 border border-transparent hover:border-cyan-500/30 transition-all cursor-pointer shadow-sm hover:shadow-[0_0_10px_rgba(0,255,255,0.1)]"
                                onClick={() => setInput(item.query_name)}
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

const HistorySidebar = () => {
    const messages = useChatStore(state => state.messages);
    const activeSidePanel = useChatStore(state => state.activeSidePanel);
    const setActiveSidePanel = useChatStore(state => state.setActiveSidePanel);

    const renderPanel = () => {
        switch (activeSidePanel) {
            case 'memory': return <MemoryPanel />;
            case 'watch': return <WatchPanel />;
            case 'plugins': return <PluginPanel />;
            case 'system': return <SystemPanel />;
            default: return <HistoryContent />;
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.5, ease: "easeOut" }}
            className={`fixed z-40 left-6 top-32 bottom-32 w-64 glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden transition-all duration-700 ${messages.length === 0 ? 'translate-y-[15vh]' : 'translate-y-0'}`}
        >
            {/* Tab Navigation */}
            <div className="flex border-b border-cyan-500/20 bg-black/30 shrink-0">
                {PANEL_TABS.map(({ id, icon: Icon, label }) => (
                    <button
                        key={id}
                        onClick={() => setActiveSidePanel(id)}
                        title={label}
                        className={`flex-1 py-2.5 flex items-center justify-center transition-all ${
                            activeSidePanel === id
                                ? 'text-cyan-300 border-b-2 border-cyan-400 bg-cyan-900/20'
                                : 'text-cyan-500/30 hover:text-cyan-400/60'
                        }`}
                    >
                        <Icon className="w-3.5 h-3.5" />
                    </button>
                ))}
            </div>

            {/* Active Panel Content */}
            <div className="flex-1 overflow-hidden flex flex-col">
                {renderPanel()}
            </div>
        </motion.div>
    );
};

export default HistorySidebar;
