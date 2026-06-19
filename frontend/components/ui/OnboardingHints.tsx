'use client';

import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PanelLeft, TerminalSquare, Radar, X } from 'lucide-react';
import { useTranslations } from 'next-intl';

const STORAGE_KEY = 'jarvis_onboarded_v1';

const STEP_META = [
    { key: 'nav', icon: PanelLeft },
    { key: 'search', icon: TerminalSquare },
    { key: 'dock', icon: Radar },
] as const;

const OnboardingHints = () => {
    const t = useTranslations('onboarding');
    const [visible, setVisible] = useState(false);
    const [step, setStep] = useState(0);

    useEffect(() => {
        try {
            if (!localStorage.getItem(STORAGE_KEY)) setVisible(true);
        } catch {
            /* localStorage unavailable — skip onboarding silently */
        }
    }, []);

    const dismiss = () => {
        setVisible(false);
        try { localStorage.setItem(STORAGE_KEY, '1'); } catch { /* ignore */ }
    };

    const isLast = step === STEP_META.length - 1;
    const { icon: Icon, key } = STEP_META[step];

    return (
        <AnimatePresence>
            {visible && (
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 30 }}
                    transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                    className="fixed bottom-28 left-1/2 -translate-x-1/2 z-[60] w-[340px] glass-strong rounded-2xl border border-cyan-500/30 shadow-[0_10px_40px_rgba(0,0,0,0.7)] overflow-hidden pointer-events-auto"
                >
                    {/* Header */}
                    <div className="flex items-center gap-2 px-4 py-2.5 border-b border-cyan-500/20 bg-cyan-900/30">
                        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                        <span className="text-[10px] font-bold font-orbitron tracking-[0.25em] text-cyan-300 uppercase glow-cyan">
                            {t('title')}
                        </span>
                        <button
                            onClick={dismiss}
                            title={t('skip')}
                            className="ml-auto p-1 rounded-md text-cyan-500/50 hover:text-cyan-200 hover:bg-cyan-500/10 transition-all"
                        >
                            <X className="w-3.5 h-3.5" />
                        </button>
                    </div>

                    {/* Body */}
                    <div className="p-4">
                        <div className="flex items-start gap-3">
                            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 shrink-0">
                                <Icon className="w-5 h-5 text-cyan-400" />
                            </div>
                            <div className="flex flex-col gap-1">
                                <span className="text-[13px] font-orbitron font-bold tracking-wider uppercase text-white">
                                    {t(`steps.${key}.title`)}
                                </span>
                                <span className="text-[12px] text-gray-400 leading-snug font-rajdhani">
                                    {t(`steps.${key}.body`)}
                                </span>
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="flex items-center justify-between mt-4">
                            <div className="flex items-center gap-1.5">
                                {STEP_META.map((_, i) => (
                                    <span
                                        key={i}
                                        className={`h-1.5 rounded-full transition-all ${i === step ? 'w-5 bg-cyan-400' : 'w-1.5 bg-cyan-500/30'}`}
                                    />
                                ))}
                            </div>
                            <div className="flex items-center gap-2">
                                {step > 0 && (
                                    <button
                                        onClick={() => setStep(step - 1)}
                                        className="px-3 py-1.5 rounded-lg text-[11px] font-bold font-mono uppercase tracking-wider text-cyan-500/60 hover:text-cyan-200 transition-all"
                                    >
                                        {t('back')}
                                    </button>
                                )}
                                <button
                                    onClick={() => (isLast ? dismiss() : setStep(step + 1))}
                                    className="px-4 py-1.5 rounded-lg text-[11px] font-bold font-mono uppercase tracking-wider bg-cyan-500/15 border border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/25 transition-all"
                                >
                                    {isLast ? t('done') : t('next')}
                                </button>
                            </div>
                        </div>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
};

export default OnboardingHints;
