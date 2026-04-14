'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Plus, Trash2, Search, X, Tag } from 'lucide-react';
import { getMemories, createMemory, deleteMemory, searchMemories } from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import { UserMemory } from '@/types/profile';
import ScrambleText from '@/components/ui/ScrambleText';
import { showError } from '@/lib/toast';

const CATEGORIES = ['preference', 'fact', 'interaction', 'personality'] as const;

const MemoryPanel = () => {
    const userMemories = useChatStore(state => state.userMemories);
    const setUserMemories = useChatStore(state => state.setUserMemories);

    const [showAdd, setShowAdd] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<UserMemory[] | null>(null);
    const [form, setForm] = useState({ category: 'fact', key: '', value: '', importance: 5 });
    const [loading, setLoading] = useState(false);

    const loadMemories = useCallback(async () => {
        try {
            const data = await getMemories();
            setUserMemories(data.memories);
        } catch (e) {
            console.error('Failed to load memories', e);
            showError('Failed to load memories.');
        }
    }, [setUserMemories]);

    useEffect(() => { loadMemories(); }, [loadMemories]);

    const handleAdd = async () => {
        if (!form.key.trim() || !form.value.trim()) return;
        setLoading(true);
        try {
            await createMemory(form.category, form.key, form.value, undefined, form.importance);
            setForm({ category: 'fact', key: '', value: '', importance: 5 });
            setShowAdd(false);
            await loadMemories();
        } catch (e) {
            console.error('Failed to create memory', e);
            showError('Failed to save memory.');
        } finally { setLoading(false); }
    };

    const handleDelete = async (id: number) => {
        try {
            await deleteMemory(id);
            setUserMemories(userMemories.filter(m => m.id !== id));
        } catch (e) {
            console.error('Failed to delete memory', e);
            showError('Failed to delete memory.');
        }
    };

    const handleSearch = async () => {
        if (!searchQuery.trim()) { setSearchResults(null); return; }
        try {
            const data = await searchMemories(searchQuery);
            setSearchResults(data.results);
        } catch (e) {
            console.error('Memory search failed', e);
            showError('Memory search failed.');
        }
    };

    const displayMemories = searchResults ?? userMemories;
    const grouped = displayMemories.reduce<Record<string, UserMemory[]>>((acc, m) => {
        (acc[m.category] ??= []).push(m);
        return acc;
    }, {});

    return (
        <div className="flex flex-col h-full">
            <div className="p-4 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2">
                <Brain className="w-5 h-5 text-purple-400" />
                <ScrambleText text="User Memory" className="text-xs font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
            </div>

            {/* Search */}
            <div className="p-3 border-b border-cyan-500/10 flex gap-2">
                <input
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSearch()}
                    placeholder="Semantic search..."
                    className="flex-1 bg-black/30 border border-cyan-500/20 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder:text-cyan-500/30 focus:outline-none focus:border-cyan-400/50"
                />
                {searchResults ? (
                    <button onClick={() => { setSearchResults(null); setSearchQuery(''); }} className="p-1.5 text-cyan-500 hover:text-red-400"><X className="w-3.5 h-3.5" /></button>
                ) : (
                    <button onClick={handleSearch} className="p-1.5 text-cyan-500 hover:text-cyan-300"><Search className="w-3.5 h-3.5" /></button>
                )}
                <button onClick={() => setShowAdd(!showAdd)} className="p-1.5 text-cyan-500 hover:text-green-400"><Plus className="w-3.5 h-3.5" /></button>
            </div>

            {/* Add Form */}
            <AnimatePresence>
                {showAdd && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-b border-cyan-500/10">
                        <div className="p-3 space-y-2">
                            <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className="w-full bg-black/40 border border-cyan-500/20 rounded-lg px-3 py-1.5 text-xs text-gray-200">
                                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                            <input value={form.key} onChange={e => setForm({ ...form, key: e.target.value })} placeholder="Key (e.g. name, preference)" className="w-full bg-black/40 border border-cyan-500/20 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder:text-cyan-500/30" />
                            <textarea value={form.value} onChange={e => setForm({ ...form, value: e.target.value })} placeholder="Value..." rows={2} className="w-full bg-black/40 border border-cyan-500/20 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder:text-cyan-500/30 resize-none" />
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] text-cyan-500/60">Importance: {form.importance}</span>
                                <input type="range" min={1} max={10} value={form.importance} onChange={e => setForm({ ...form, importance: +e.target.value })} className="w-24 accent-cyan-500" />
                            </div>
                            <button onClick={handleAdd} disabled={loading} className="w-full py-1.5 bg-cyan-900/60 hover:bg-cyan-800/60 border border-cyan-500/30 rounded-lg text-xs text-cyan-300 font-mono transition-colors disabled:opacity-40">
                                {loading ? 'Storing...' : 'Store Memory'}
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Memory List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar">
                {displayMemories.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-cyan-500/40">
                        <Brain className="w-8 h-8 mb-2" />
                        <p className="text-[10px] font-mono tracking-widest uppercase">No Memories</p>
                    </div>
                ) : (
                    Object.entries(grouped).map(([cat, mems]) => (
                        <div key={cat}>
                            <div className="flex items-center gap-1.5 mb-1.5">
                                <Tag className="w-3 h-3 text-purple-400/60" />
                                <span className="text-[10px] text-purple-300/80 font-mono uppercase tracking-widest">{cat}</span>
                                <span className="text-[9px] text-cyan-500/40">({mems.length})</span>
                            </div>
                            <AnimatePresence>
                                {mems.map(m => (
                                    <motion.div key={m.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                                        className="group flex items-start justify-between p-2 mb-1 rounded-lg hover:bg-cyan-900/30 border border-transparent hover:border-cyan-500/20 transition-all"
                                    >
                                        <div className="overflow-hidden">
                                            <p className="text-[11px] text-cyan-300 font-medium truncate">{m.key}</p>
                                            <p className="text-[10px] text-gray-400 line-clamp-2">{m.value}</p>
                                        </div>
                                        <button onClick={() => handleDelete(m.id)} className="opacity-0 group-hover:opacity-100 p-1 text-cyan-700 hover:text-red-400 transition-all shrink-0 ml-2">
                                            <Trash2 className="w-3 h-3" />
                                        </button>
                                    </motion.div>
                                ))}
                            </AnimatePresence>
                        </div>
                    ))
                )}
            </div>

            <div className="px-4 py-2 border-t border-cyan-500/20 text-center bg-black/20">
                <span className="text-[9px] text-cyan-500/60 font-mono tracking-widest uppercase">{userMemories.length} memories stored</span>
            </div>
        </div>
    );
};

export default MemoryPanel;
