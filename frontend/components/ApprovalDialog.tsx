'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SearchResponse } from '@/types/profile';
import { Check, X, Database } from 'lucide-react';

interface ApprovalDialogProps {
    profile: SearchResponse;
    isOpen: boolean;
    onApprove: () => void;
    onReject: () => void;
}

export default function ApprovalDialog({
    profile,
    isOpen,
    onApprove,
    onReject
}: ApprovalDialogProps) {
    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/80 backdrop-blur-md z-40"
                        onClick={onReject}
                        aria-hidden="true"
                    />

                    {/* Dialog */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 20 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 20 }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                        className="fixed inset-0 z-50 flex items-center justify-center p-4"
                        onKeyDown={(e) => e.key === 'Escape' && onReject()}
                    >
                        <div role="dialog" aria-modal="true" aria-labelledby="approval-dialog-title" className="glass-strong rounded-2xl p-8 max-w-md w-full relative overflow-hidden group border-cyan-500/30">
                            {/* Tech accents */}
                            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent opacity-50" />
                            <div className="absolute top-0 left-0 w-16 h-16 border-t-2 border-l-2 border-cyan-400 opacity-30 rounded-tl-2xl" />
                            <div className="absolute bottom-0 right-0 w-16 h-16 border-b-2 border-r-2 border-cyan-400 opacity-30 rounded-br-2xl" />

                            {/* Header */}
                            <div className="mb-6 flex items-start gap-4 border-b border-cyan-500/10 pb-4">
                                <div className="p-3 rounded-xl bg-cyan-950/50 border border-cyan-500/30">
                                    <Database className="w-6 h-6 text-cyan-400 animate-pulse" />
                                </div>
                                <div>
                                    <h3 id="approval-dialog-title" className="text-xl font-orbitron font-bold text-white tracking-widest uppercase mb-1">
                                        Archive Data
                                    </h3>
                                    <p className="text-cyan-400/60 font-mono text-xs tracking-wider uppercase">
                                        Awaiting authorization
                                    </p>
                                </div>
                            </div>

                            {/* Profile Summary */}
                            <div className="mb-8 p-5 bg-cyan-950/20 rounded-xl border border-cyan-900/50">
                                <p className="text-cyan-400 font-bold mb-3 tracking-widest uppercase">{profile.name}</p>
                                <div className="space-y-2 text-xs font-mono tracking-wider text-gray-400">
                                    {profile.github_url && (
                                        <div className="flex items-center gap-2"><Check className="w-3 h-3 text-cyan-500" /> GITHUB NODE EXTRACTED</div>
                                    )}
                                    {profile.instagram_url && (
                                        <div className="flex items-center gap-2"><Check className="w-3 h-3 text-cyan-500" /> INSTAGRAM NODE EXTRACTED</div>
                                    )}
                                    {profile.twitter_url && (
                                        <div className="flex items-center gap-2"><Check className="w-3 h-3 text-cyan-500" /> X NODE EXTRACTED</div>
                                    )}
                                    {profile.linkedin_url && (
                                        <div className="flex items-center gap-2"><Check className="w-3 h-3 text-cyan-500" /> LINKEDIN NODE EXTRACTED</div>
                                    )}
                                    {profile.description && (
                                        <div className="flex items-center gap-2"><Check className="w-3 h-3 text-cyan-500" /> PROFILE SUMMARY GENERATED</div>
                                    )}
                                </div>
                            </div>

                            {/* Buttons */}
                            <div className="flex gap-4">
                                <motion.button
                                    whileHover={{ scale: 1.02 }}
                                    whileTap={{ scale: 0.98 }}
                                    onClick={onReject}
                                    className="flex-1 btn-jarvis bg-red-950/20 border-red-900/50 text-red-400 hover:bg-red-900/40 hover:border-red-500/50 flex items-center justify-center gap-2 font-mono text-sm tracking-widest rounded-xl"
                                >
                                    <X className="w-4 h-4" />
                                    DISCARD
                                </motion.button>

                                <motion.button
                                    whileHover={{ scale: 1.02 }}
                                    whileTap={{ scale: 0.98 }}
                                    onClick={onApprove}
                                    className="flex-1 btn-jarvis bg-cyan-950/40 border-cyan-500/50 hover:bg-cyan-900/60 hover:border-cyan-400 flex items-center justify-center gap-2 font-mono text-sm tracking-widest rounded-xl shadow-[0_0_15px_rgba(0,243,255,0.1)]"
                                >
                                    <Check className="w-4 h-4" />
                                    AUTHORIZE
                                </motion.button>
                            </div>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}
