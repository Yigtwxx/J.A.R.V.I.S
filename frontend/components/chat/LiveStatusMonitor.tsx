'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useChatStore } from '@/store/chatStore';

const LiveStatusMonitor = () => {
    const liveStatus = useChatStore(state => state.liveStatus);
    const isLoading = useChatStore(state => state.isLoading);

    if (!isLoading) return null;

    return (
        <motion.div
            initial={{ opacity: 0, x: 50 }}
            animate={{ opacity: 1, x: 0 }}
            className="w-full glass-strong rounded-[1.5rem] border border-cyan-500/40 bg-cyan-950/30 backdrop-blur-xl shadow-[0_0_30px_rgba(0,255,255,0.1)] flex flex-col overflow-hidden"
        >
            <div className="p-4 border-b border-cyan-500/30 bg-cyan-900/50 flex items-center gap-3 relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/10 to-transparent -translate-x-full animate-[shimmer_2s_infinite]" />
                <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_cyan]" />
                <span className="text-[11px] font-black font-orbitron tracking-[0.2em] text-cyan-300 uppercase glow-cyan">Live Monitoring</span>
            </div>
            <div className="p-4 space-y-3 font-mono">
                <AnimatePresence>
                    {liveStatus.map((status, idx) => (
                        <motion.div
                            key={`${status}-${idx}`}
                            initial={{ opacity: 0, x: 10, filter: 'blur(4px)' }}
                            animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
                            exit={{ opacity: 0, x: -10, filter: 'blur(4px)' }}
                            transition={{ duration: 0.3 }}
                            className="text-[10px] leading-relaxed flex gap-2 items-start"
                        >
                            <span className="text-cyan-500 shrink-0 select-none opacity-50">[{new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}]</span>
                            <span className={`${status.includes('[OK]') ? 'text-green-400' : status.includes('[ERR]') ? 'text-red-400' : 'text-cyan-100/80'} break-words`}>
                                {status.replace(/\[(SYS|OK|ERR|PROCESS|WARN)\]\s*/, '')}
                            </span>
                        </motion.div>
                    ))}
                </AnimatePresence>
                <motion.div
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ repeat: Infinity, duration: 1 }}
                    className="w-full h-px bg-cyan-500/30 mt-4"
                />
            </div>
        </motion.div>
    );
};

export default LiveStatusMonitor;
