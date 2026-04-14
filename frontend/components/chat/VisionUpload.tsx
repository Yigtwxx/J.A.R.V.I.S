'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Camera, X, Loader2, Eye, FileText, Users } from 'lucide-react';
import { analyzeImage, analyzeSocialPhoto, readScreenshot } from '@/services/api';

type AnalysisType = 'general' | 'social' | 'screenshot';

interface VisionUploadProps {
    onResult: (result: string) => void;
}

const VisionUpload = ({ onResult }: VisionUploadProps) => {
    const [open, setOpen] = useState(false);
    const [imageUrl, setImageUrl] = useState('');
    const [prompt, setPrompt] = useState('');
    const [analysisType, setAnalysisType] = useState<AnalysisType>('general');
    const [loading, setLoading] = useState(false);

    const handleAnalyze = async () => {
        if (!imageUrl.trim()) return;
        setLoading(true);
        try {
            let resultText: string;
            if (analysisType === 'general') {
                const data = await analyzeImage(imageUrl, prompt || undefined);
                resultText = typeof data.analysis === 'string' ? data.analysis : JSON.stringify(data.analysis, null, 2);
            } else if (analysisType === 'social') {
                const data = await analyzeSocialPhoto(imageUrl);
                resultText = typeof data.analysis === 'string' ? data.analysis : JSON.stringify(data.analysis, null, 2);
            } else {
                const data = await readScreenshot(imageUrl);
                resultText = data.text;
            }
            onResult(`**Vision Analysis (${analysisType}):**\n\n${resultText}`);
            setOpen(false);
            setImageUrl('');
            setPrompt('');
        } catch (e: unknown) {
            const errMsg = e instanceof Error ? e.message : 'Unknown error';
            onResult(`[Vision Error] ${errMsg}`);
        } finally { setLoading(false); }
    };

    return (
        <>
            <button onClick={() => setOpen(!open)} title="Vision Analysis"
                className={`p-2 rounded-lg border transition-all ${open ? 'border-purple-500/50 bg-purple-900/30 text-purple-300' : 'border-cyan-500/20 text-cyan-500/40 hover:text-cyan-300 hover:border-cyan-500/40'}`}
            >
                <Camera className="w-4 h-4" />
            </button>

            <AnimatePresence>
                {open && (
                    <motion.div
                        initial={{ opacity: 0, y: 10, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 10, scale: 0.95 }}
                        className="absolute bottom-full mb-2 left-0 right-0 p-4 rounded-2xl border border-cyan-500/30 bg-gray-950/95 backdrop-blur-md shadow-[0_0_30px_rgba(0,0,0,0.8)]"
                    >
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-[11px] font-mono text-cyan-300 uppercase tracking-wider">Vision Analysis</span>
                            <button onClick={() => setOpen(false)} className="text-cyan-500/40 hover:text-red-400"><X className="w-3.5 h-3.5" /></button>
                        </div>

                        {/* Analysis type */}
                        <div className="flex gap-1 mb-3">
                            {([
                                { type: 'general' as const, icon: Eye, label: 'General' },
                                { type: 'social' as const, icon: Users, label: 'Social OSINT' },
                                { type: 'screenshot' as const, icon: FileText, label: 'OCR' },
                            ]).map(({ type, icon: Icon, label }) => (
                                <button key={type} onClick={() => setAnalysisType(type)}
                                    className={`flex-1 py-1.5 rounded-lg text-[10px] font-mono flex items-center justify-center gap-1 border transition-colors ${analysisType === type ? 'border-cyan-500/40 bg-cyan-900/30 text-cyan-300' : 'border-cyan-500/10 text-cyan-500/40 hover:text-cyan-400/60'}`}
                                >
                                    <Icon className="w-3 h-3" /> {label}
                                </button>
                            ))}
                        </div>

                        <input value={imageUrl} onChange={e => setImageUrl(e.target.value)} placeholder="Image URL..."
                            className="w-full bg-black/40 border border-cyan-500/20 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder:text-cyan-500/30 focus:outline-none focus:border-cyan-400/50 mb-2"
                        />

                        {analysisType === 'general' && (
                            <input value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Custom prompt (optional)..."
                                className="w-full bg-black/40 border border-cyan-500/20 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder:text-cyan-500/30 focus:outline-none focus:border-cyan-400/50 mb-2"
                            />
                        )}

                        <button onClick={handleAnalyze} disabled={loading || !imageUrl.trim()}
                            className="w-full py-2 bg-cyan-900/60 hover:bg-cyan-800/60 border border-cyan-500/30 rounded-lg text-xs text-cyan-300 font-mono transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                        >
                            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Camera className="w-3 h-3" />}
                            {loading ? 'Analyzing...' : 'Analyze Image'}
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
};

export default VisionUpload;
