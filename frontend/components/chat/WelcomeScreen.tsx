'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
    Search, Bot, ScanFace, Brain, Eye, Puzzle, Terminal, Heart,
    Github, ShieldAlert, MapPin, Video, Users, Smile, TrendingUp, FileDown,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useChatStore, SidePanel } from '@/store/chatStore';
import GlitchText from '@/components/ui/GlitchText';

type CapabilityCard = {
    key: string;
    icon: typeof Search;
    accent: string;
    action?: () => void;
};

const WelcomeScreen = () => {
    const t = useTranslations('welcome');
    const setInput = useChatStore(state => state.setInput);
    const setActiveSidePanel = useChatStore(state => state.setActiveSidePanel);
    const setAgentMode = useChatStore(state => state.setAgentMode);

    const openPanel = (panel: Exclude<SidePanel, null>) => () => setActiveSidePanel(panel);

    const cards: CapabilityCard[] = [
        { key: 'search', icon: Search, accent: 'text-cyan-400' },
        { key: 'agent', icon: Bot, accent: 'text-purple-400', action: () => setAgentMode(true) },
        { key: 'vision', icon: ScanFace, accent: 'text-blue-400' },
        { key: 'memory', icon: Brain, accent: 'text-fuchsia-400', action: openPanel('memory') },
        { key: 'watch', icon: Eye, accent: 'text-emerald-400', action: openPanel('watch') },
        { key: 'plugins', icon: Puzzle, accent: 'text-orange-400', action: openPanel('plugins') },
        { key: 'system', icon: Terminal, accent: 'text-red-400', action: openPanel('system') },
        { key: 'health', icon: Heart, accent: 'text-rose-400', action: openPanel('health') },
    ];

    // Analysis modules surfaced automatically inside each dossier
    const modules: { icon: typeof Github; label: string }[] = [
        { icon: Github, label: t('modSocial') },
        { icon: ShieldAlert, label: t('modBreach') },
        { icon: MapPin, label: t('modGeo') },
        { icon: Video, label: t('modCameras') },
        { icon: ScanFace, label: t('modFace') },
        { icon: Users, label: t('modNetwork') },
        { icon: Smile, label: t('modSentiment') },
        { icon: TrendingUp, label: t('modPredictive') },
        { icon: FileDown, label: t('modExport') },
    ];

    const examples = ['Ada Lovelace', 'Linus Torvalds', 'Grace Hopper', 'Tim Berners-Lee'];

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6 }}
            className="w-full max-w-5xl mx-auto px-4 py-10 flex flex-col items-center text-center"
        >
            {/* Hero */}
            <motion.div
                initial={{ opacity: 0, y: 20, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                className="flex flex-col items-center gap-4 mb-10"
            >
                <div className="relative w-20 h-20 rounded-2xl overflow-hidden border-2 border-cyan-500/60 shadow-[0_0_35px_rgba(0,255,255,0.35)] bg-black/40 flex items-center justify-center animate-pulse-glow">
                    <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/25 to-transparent" />
                    <span className="text-4xl font-black text-cyan-400 font-orbitron glow-cyan select-none">J</span>
                </div>
                <h1 className="text-4xl md:text-6xl font-black tracking-[0.25em] uppercase font-orbitron">
                    <GlitchText
                        text="J.A.R.V.I.S"
                        interval={5000}
                        className="text-transparent bg-clip-text bg-gradient-to-r from-white via-cyan-100 to-cyan-400"
                    />
                </h1>
                <p className="text-cyan-300/80 text-[11px] md:text-xs font-bold uppercase tracking-[0.4em] glow-cyan font-mono">
                    {t('tagline')}
                </p>
                <p className="text-gray-400 max-w-xl text-sm md:text-[15px] leading-relaxed mt-2 font-rajdhani">
                    {t('intro')}
                </p>
            </motion.div>

            {/* Capability cards */}
            <div className="w-full grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3.5 mb-10">
                {cards.map(({ key, icon: Icon, accent, action }, idx) => (
                    <motion.div
                        key={key}
                        initial={{ opacity: 0, y: 18 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.15 + idx * 0.05 }}
                        onClick={action}
                        role={action ? 'button' : undefined}
                        tabIndex={action ? 0 : undefined}
                        onKeyDown={action ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); action(); } } : undefined}
                        className={`capability-card p-4 flex flex-col items-start gap-2 text-left ${action ? 'cursor-pointer' : ''}`}
                    >
                        <Icon className={`w-6 h-6 ${accent} drop-shadow-[0_0_8px_currentColor]`} />
                        <span className="text-[12px] font-orbitron font-bold tracking-wider uppercase text-white mt-1">
                            {t(`cards.${key}.title`)}
                        </span>
                        <span className="text-[11px] text-gray-400 leading-snug font-rajdhani">
                            {t(`cards.${key}.desc`)}
                        </span>
                    </motion.div>
                ))}
            </div>

            {/* Example searches */}
            <div className="w-full mb-9">
                <div className="flex items-center justify-center gap-2 mb-3">
                    <span className="h-px w-8 bg-cyan-500/30" />
                    <span className="text-[10px] font-bold font-mono tracking-[0.3em] text-cyan-500/60 uppercase">{t('examplesLabel')}</span>
                    <span className="h-px w-8 bg-cyan-500/30" />
                </div>
                <div className="flex flex-wrap items-center justify-center gap-2.5">
                    {examples.map((ex) => (
                        <button
                            key={ex}
                            onClick={() => setInput(ex)}
                            className="example-chip px-4 py-2 rounded-full text-[13px] font-medium text-cyan-100/90 tracking-wide flex items-center gap-2"
                        >
                            <Search className="w-3.5 h-3.5 text-cyan-400/70" />
                            {ex}
                        </button>
                    ))}
                </div>
            </div>

            {/* Auto-generated module strip */}
            <div className="w-full">
                <div className="flex items-center justify-center gap-2 mb-3">
                    <span className="h-px w-8 bg-cyan-500/20" />
                    <span className="text-[10px] font-bold font-mono tracking-[0.3em] text-cyan-500/50 uppercase">{t('modulesLabel')}</span>
                    <span className="h-px w-8 bg-cyan-500/20" />
                </div>
                <div className="flex flex-wrap items-center justify-center gap-2">
                    {modules.map(({ icon: Icon, label }) => (
                        <span
                            key={label}
                            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-white/8 bg-white/[0.02] text-[10px] font-mono tracking-wider text-gray-400 uppercase"
                        >
                            <Icon className="w-3 h-3 text-cyan-400/60" />
                            {label}
                        </span>
                    ))}
                </div>
            </div>
        </motion.div>
    );
};

export default WelcomeScreen;
