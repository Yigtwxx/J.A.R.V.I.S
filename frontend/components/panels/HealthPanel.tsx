'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Heart, Plus, Send, Activity, Moon, Zap, Pill, Dumbbell, Smile, Apple, X, Loader2, AlertTriangle } from 'lucide-react';
import {
    getHealthCategories, getHealthHistory, recordHealthData, getHealthSuggestions,
    HealthCategory, HealthRecord, HealthSuggestions,
} from '@/services/api';
import ScrambleText from '@/components/ui/ScrambleText';
import { showError } from '@/lib/toast';

const QUICK_ENTRIES = [
    { cat: 'health_sleep', key: 'sleep_hours', label: 'Slept 6h', value: '6 hours' },
    { cat: 'health_sleep', key: 'sleep_hours', label: 'Slept 8h', value: '8 hours' },
    { cat: 'health_energy', key: 'energy_level', label: 'Low energy', value: 'Low' },
    { cat: 'health_energy', key: 'energy_level', label: 'High energy', value: 'High' },
    { cat: 'health_mood', key: 'mood', label: 'Feeling good', value: 'Good / positive' },
    { cat: 'health_mood', key: 'mood', label: 'Stressed', value: 'Stressed / anxious' },
    { cat: 'health_illness', key: 'symptom', label: 'Headache', value: 'Headache' },
    { cat: 'health_illness', key: 'symptom', label: 'Tired', value: 'Feeling tired / fatigued' },
];

const catIcon = (cat: string) => {
    if (cat.includes('sleep')) return <Moon size={10} className="text-indigo-400" />;
    if (cat.includes('energy')) return <Zap size={10} className="text-yellow-400" />;
    if (cat.includes('illness')) return <Pill size={10} className="text-red-400" />;
    if (cat.includes('exercise')) return <Dumbbell size={10} className="text-emerald-400" />;
    if (cat.includes('mood')) return <Smile size={10} className="text-pink-400" />;
    if (cat.includes('nutrition')) return <Apple size={10} className="text-orange-400" />;
    if (cat.includes('vitals')) return <Activity size={10} className="text-cyan-400" />;
    return <Heart size={10} className="text-red-400" />;
};

const HealthPanel = () => {
    const [categories, setCategories] = useState<HealthCategory[]>([]);
    const [history, setHistory] = useState<HealthRecord[]>([]);
    const [selectedCat, setSelectedCat] = useState<string | null>(null);
    const [showAdd, setShowAdd] = useState(false);
    const [form, setForm] = useState({ category: 'health_energy', key: '', value: '' });
    const [loading, setLoading] = useState(false);

    // Ask JARVIS
    const [askInput, setAskInput] = useState('');
    const [suggestions, setSuggestions] = useState<HealthSuggestions | null>(null);
    const [askLoading, setAskLoading] = useState(false);

    const loadData = useCallback(async () => {
        try {
            const [cats, hist] = await Promise.all([
                getHealthCategories(),
                getHealthHistory(selectedCat || undefined, 30),
            ]);
            setCategories(cats);
            setHistory(hist);
        } catch (e) {
            console.error('Failed to load health data', e);
            showError('Failed to load health data.');
        }
    }, [selectedCat]);

    useEffect(() => { loadData(); }, [loadData]);

    const handleQuickEntry = async (entry: typeof QUICK_ENTRIES[0]) => {
        setLoading(true);
        try {
            await recordHealthData(entry.cat, entry.key, entry.value);
            await loadData();
        } catch (e) {
            console.error('Quick entry failed', e);
            showError('Failed to record health entry.');
        } finally { setLoading(false); }
    };

    const handleAdd = async () => {
        if (!form.key.trim() || !form.value.trim()) return;
        setLoading(true);
        try {
            await recordHealthData(form.category, form.key, form.value);
            setForm({ category: 'health_energy', key: '', value: '' });
            setShowAdd(false);
            await loadData();
        } catch (e) {
            console.error('Failed to record health data', e);
            showError('Failed to record health data.');
        } finally { setLoading(false); }
    };

    const handleAskJarvis = async () => {
        if (!askInput.trim()) return;
        setAskLoading(true);
        try {
            const result = await getHealthSuggestions(askInput.trim());
            setSuggestions(result);
        } catch (e) {
            console.error('Failed to get suggestions', e);
            showError('Failed to get health suggestions.');
        } finally { setAskLoading(false); }
    };

    const filtered = selectedCat ? history.filter(r => r.category === selectedCat) : history;

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="p-3 border-b border-red-500/10 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Heart size={14} className="text-red-400" />
                    <span className="text-xs font-mono text-red-300">
                        <ScrambleText text="HEALTH" />
                    </span>
                    <span className="text-[9px] text-gray-500 font-mono">{history.length}</span>
                </div>
                <button
                    onClick={() => setShowAdd(!showAdd)}
                    className="text-red-400 hover:text-red-300 transition-colors"
                >
                    {showAdd ? <X size={14} /> : <Plus size={14} />}
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-2 custom-scrollbar">
                {/* Quick Entries */}
                <div className="flex flex-wrap gap-1">
                    {QUICK_ENTRIES.map((entry, i) => (
                        <button
                            key={i}
                            onClick={() => handleQuickEntry(entry)}
                            disabled={loading}
                            className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-red-900/30 bg-red-950/20 text-red-300/70 hover:bg-red-900/30 hover:text-red-200 transition-all disabled:opacity-30"
                        >
                            {entry.label}
                        </button>
                    ))}
                </div>

                {/* Add Form */}
                <AnimatePresence>
                    {showAdd && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="space-y-1.5 overflow-hidden"
                        >
                            <select
                                value={form.category}
                                onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                                className="w-full text-[10px] font-mono bg-black/50 border border-red-900/30 rounded p-1 text-gray-300"
                            >
                                {categories.map(c => (
                                    <option key={c.id} value={c.id}>{c.label}</option>
                                ))}
                            </select>
                            <input
                                placeholder="Label (e.g. sleep_hours)"
                                value={form.key}
                                onChange={e => setForm(f => ({ ...f, key: e.target.value }))}
                                className="w-full text-[10px] font-mono bg-black/50 border border-red-900/30 rounded p-1 text-gray-300 placeholder-gray-600"
                            />
                            <input
                                placeholder="Value (e.g. 7 hours)"
                                value={form.value}
                                onChange={e => setForm(f => ({ ...f, value: e.target.value }))}
                                className="w-full text-[10px] font-mono bg-black/50 border border-red-900/30 rounded p-1 text-gray-300 placeholder-gray-600"
                            />
                            <button
                                onClick={handleAdd}
                                disabled={loading || !form.key.trim() || !form.value.trim()}
                                className="w-full text-[10px] font-mono py-1 rounded bg-red-900/40 text-red-300 hover:bg-red-800/50 transition-colors disabled:opacity-30"
                            >
                                {loading ? 'Recording...' : 'Record'}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Category Filter */}
                <div className="flex flex-wrap gap-1">
                    <button
                        onClick={() => setSelectedCat(null)}
                        className={`text-[9px] font-mono px-1.5 py-0.5 rounded transition-all ${
                            !selectedCat ? 'bg-red-900/40 text-red-300' : 'text-gray-500 hover:text-gray-400'
                        }`}
                    >
                        All
                    </button>
                    {categories.map(c => (
                        <button
                            key={c.id}
                            onClick={() => setSelectedCat(c.id)}
                            className={`text-[9px] font-mono px-1.5 py-0.5 rounded flex items-center gap-1 transition-all ${
                                selectedCat === c.id ? 'bg-red-900/40 text-red-300' : 'text-gray-500 hover:text-gray-400'
                            }`}
                        >
                            {catIcon(c.id)}
                            {c.label.split(' ')[0]}
                        </button>
                    ))}
                </div>

                {/* History List */}
                <div className="space-y-1">
                    {filtered.map((r, i) => (
                        <motion.div
                            key={r.id || i}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: i * 0.03 }}
                            className="bg-black/30 border border-red-900/20 rounded p-1.5"
                        >
                            <div className="flex items-center gap-1.5">
                                {catIcon(r.category)}
                                <span className="text-[10px] text-gray-300 font-mono flex-1 truncate">{r.key}</span>
                            </div>
                            <p className="text-[10px] text-gray-400 mt-0.5 pl-4">{r.value}</p>
                        </motion.div>
                    ))}
                    {filtered.length === 0 && (
                        <p className="text-[10px] text-gray-600 font-mono text-center py-4">
                            No health data recorded yet.
                        </p>
                    )}
                </div>

                {/* Ask JARVIS */}
                <div className="border-t border-red-900/20 pt-2 mt-2">
                    <div className="flex items-center gap-1.5 mb-1.5">
                        <Heart size={10} className="text-red-400" />
                        <span className="text-[9px] font-mono text-red-400 uppercase">Ask J.A.R.V.I.S</span>
                    </div>
                    <div className="flex gap-1">
                        <input
                            placeholder="How are you feeling?"
                            value={askInput}
                            onChange={e => setAskInput(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleAskJarvis()}
                            className="flex-1 text-[10px] font-mono bg-black/50 border border-red-900/30 rounded p-1 text-gray-300 placeholder-gray-600"
                        />
                        <button
                            onClick={handleAskJarvis}
                            disabled={askLoading || !askInput.trim()}
                            className="px-2 rounded bg-red-900/40 text-red-300 hover:bg-red-800/50 transition-colors disabled:opacity-30"
                        >
                            {askLoading ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                        </button>
                    </div>

                    {/* Suggestions */}
                    <AnimatePresence>
                        {suggestions && (
                            <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="mt-2 space-y-1.5 overflow-hidden"
                            >
                                <p className="text-[10px] text-gray-300">{suggestions.assessment}</p>
                                {suggestions.suggestions.map((s, i) => (
                                    <div key={i} className="text-[10px] text-emerald-300/80 flex items-start gap-1.5 pl-1">
                                        <span className="text-emerald-500 shrink-0">+</span> {s}
                                    </div>
                                ))}
                                {suggestions.warnings.length > 0 && suggestions.warnings.map((w, i) => (
                                    <div key={i} className="text-[10px] text-orange-300/80 flex items-start gap-1.5 pl-1">
                                        <AlertTriangle size={10} className="text-orange-500 shrink-0 mt-0.5" /> {w}
                                    </div>
                                ))}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </div>
    );
};

export default HealthPanel;
