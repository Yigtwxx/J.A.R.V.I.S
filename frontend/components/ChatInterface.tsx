'use client';

import React, { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Loader2, TerminalSquare, Save, CheckCircle, History, Trash2, Clock, Github, Instagram, Twitter, Linkedin, Globe, Mic, MicOff, Volume2, VolumeX, MapPin, Thermometer, Cloud, Sun, Wind, Search } from 'lucide-react';
import { searchPerson, saveProfile, getSearchHistory, deleteHistoryItem } from '@/services/api';
import { Message, SearchResponse } from '@/types/profile';
import ReactMarkdown from 'react-markdown';
import dynamic from 'next/dynamic';
import { useChatStore } from '@/store/chatStore';
import ScrambleText from '@/components/ui/ScrambleText';
import GlitchText from '@/components/ui/GlitchText';

// Lazy-loaded Heavy Components
const ProfileCard = dynamic(() => import('./ProfileCard'), { ssr: false });
const VersionHistory = dynamic(() => import('./VersionHistory'), { ssr: false });
const FaceMatch = dynamic(() => import('./FaceMatch'), { ssr: false });
const SocialGauge = dynamic(() => import('./SocialGauge'), { ssr: false });
const SentimentGauge = dynamic(() => import('./SentimentGauge'), { ssr: false });
const LoadingAnimation = dynamic(() => import('./LoadingAnimation'), { ssr: false });

// Custom Brand Icons
import { SpotifyIcon, TikTokIcon, SnapchatIcon, TumblrIcon, TinderIcon,
         BumbleIcon, YoutubeIcon, RedditIcon, FacebookIcon, PhoneIcon,
         PinterestIcon, MediumIcon, ThreadsIcon, SteamIcon, DiscordIcon } from '@/components/ui/Icons';

const LiveStatusMonitor = () => {
    const liveStatus = useChatStore(state => state.liveStatus);
    const isLoading = useChatStore(state => state.isLoading);

    if (!isLoading) return null;

    return (
        <motion.div
            initial={{ opacity: 0, x: 50 }}
            animate={{ opacity: 1, x: 0 }}
            className="fixed z-40 right-6 top-6 w-64 glass-strong rounded-[1.5rem] border border-cyan-500/40 bg-cyan-950/30 backdrop-blur-xl shadow-[0_0_30px_rgba(0,255,255,0.1)] flex flex-col overflow-hidden"
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

const StreamingMessageBubble = () => {
    const streamingContent = useChatStore(state => state.streamingContent);
    const isLoading = useChatStore(state => state.isLoading);

    useEffect(() => {
        document.getElementById('messages-end')?.scrollIntoView({ behavior: 'smooth' });
    }, [streamingContent]);

    if (!isLoading || !streamingContent) return null;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex justify-start"
        >
            <div className="w-full max-w-3xl space-y-6">
                <div className="message-bubble message-ai text-white font-mono text-[15px] leading-normal tracking-wide shadow-lg border-l-4 border-cyan-400 relative">
                    <div className="flex items-center gap-2 mb-3 text-cyan-400 font-bold pb-2 border-b border-cyan-500/30">
                        <TerminalSquare className="w-5 h-5 glow-cyan animate-pulse" />
                        <span className="text-sm uppercase tracking-[0.2em] glow-cyan">Receiving Transmission...</span>
                    </div>
                    <ReactMarkdown
                        components={{
                            p: ({ children, ...props }) => <p className="leading-normal text-gray-200 mb-2 last:mb-0" {...props}>{children}</p>,
                        }}
                    >
                        {streamingContent}
                    </ReactMarkdown>
                    <span className="inline-block w-2.5 h-4 ml-1 bg-cyan-400 animate-pulse align-middle shadow-[0_0_8px_cyan]" />
                </div>
            </div>
        </motion.div>
    );
};

const RagStreamingBubble = () => {
    const streamingRagContent = useChatStore(state => state.streamingRagContent);
    const isRagLoading = useChatStore(state => state.isRagLoading);

    useEffect(() => {
        document.getElementById('messages-end')?.scrollIntoView({ behavior: 'smooth' });
    }, [streamingRagContent]);

    if (!isRagLoading) return null;

    return (
        <div className="flex justify-start">
            <div className="p-3.5 rounded-xl max-w-[90%] md:max-w-[80%] font-mono text-sm bg-teal-950/30 text-teal-50 border-l-4 border-teal-500 shadow-[0_4px_15px_rgba(45,212,191,0.1)]">
                {streamingRagContent ? (
                    <ReactMarkdown components={{ p: ({ children, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props}>{children}</p> }}>
                        {streamingRagContent}
                    </ReactMarkdown>
                ) : (
                    <div className="flex items-center gap-2 text-teal-400/80">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="uppercase tracking-widest text-xs">Querying deep context nodes...</span>
                    </div>
                )}
            </div>
        </div>
    );
};

const HistorySidebar = () => {
    const history = useChatStore(state => state.history);
    const setHistory = useChatStore(state => state.setHistory);
    const setInput = useChatStore(state => state.setInput);
    const messages = useChatStore(state => state.messages);

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
        <motion.div
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.5, ease: "easeOut" }}
            className={`fixed z-40 left-6 top-32 bottom-32 w-64 glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden transition-all duration-700 ${messages.length === 0 ? 'translate-y-[15vh]' : 'translate-y-0'}`}
        >
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
        </motion.div>
    );
};

const RagInteractionPanel = ({ profileName }: { profileName: string }) => {
    const ragInput = useChatStore(state => state.ragInput);
    const setRagInput = useChatStore(state => state.setRagInput);
    const ragMessages = useChatStore(state => state.ragMessages);
    const setRagMessages = useChatStore(state => state.setRagMessages);
    const isRagLoading = useChatStore(state => state.isRagLoading);
    const setIsRagLoading = useChatStore(state => state.setIsRagLoading);
    const setStreamingRagContent = useChatStore(state => state.setStreamingRagContent);

    const handleRagSubmit = async () => {
        if (!ragInput.trim() || isRagLoading) return;

        const userMessage = { role: 'user' as const, content: ragInput.trim() };
        setRagMessages(prev => [...prev, userMessage]);
        setRagInput('');
        setIsRagLoading(true);
        setStreamingRagContent('');

        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/chat/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query_name: profileName,
                    messages: ragMessages.concat(userMessage)
                })
            });

            if (!response.ok) throw new Error('RAG Chat failed');

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let aiContent = '';

            if (reader) {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    aiContent += chunk;
                    setStreamingRagContent(aiContent);
                }
            }

            setRagMessages(prev => [...prev, { role: 'assistant', content: aiContent }]);
            setStreamingRagContent('');

        } catch (error) {
            console.error(error);
            setRagMessages(prev => [...prev, { role: 'assistant', content: '[SYSTEM ERROR: Neural reasoning engine failure. Check API logs.]' }]);
            setStreamingRagContent('');
        } finally {
            setIsRagLoading(false);
        }
    };

    return (
        <div className="mt-8 border-t-2 border-cyan-500/20 pt-5">
            <div className="flex items-center gap-2 mb-4">
                <TerminalSquare className="w-5 h-5 text-teal-400 drop-shadow-[0_0_8px_rgba(45,212,191,0.8)]" />
                <span className="text-sm font-bold font-mono text-teal-300 uppercase tracking-widest drop-shadow-[0_0_5px_rgba(45,212,191,0.5)]">
                    Interactive Analysis Protocol
                </span>
            </div>

            <div className="space-y-4 mb-4">
                {ragMessages.map((ragMsg, rIndex) => (
                    <div key={rIndex} className={`flex ${ragMsg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`p-3.5 rounded-xl max-w-[90%] md:max-w-[80%] font-mono text-sm shadow-md ${ragMsg.role === 'user' ? 'bg-cyan-950/40 text-cyan-50 border border-cyan-500/30' : 'bg-teal-950/30 text-teal-50 border-l-4 border-teal-500 shadow-[0_4px_15px_rgba(45,212,191,0.1)]'}`}>
                            {ragMsg.role === 'assistant' ? (
                                <ReactMarkdown components={{ p: ({ children, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props}>{children}</p> }}>
                                    {ragMsg.content}
                                </ReactMarkdown>
                            ) : ragMsg.content}
                        </div>
                    </div>
                ))}

                <RagStreamingBubble />
            </div>

            <div className="flex gap-2">
                <input
                    type="text"
                    value={ragInput}
                    onChange={(e) => setRagInput(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRagSubmit();
                    }}
                    disabled={isRagLoading}
                    placeholder={`Ask J.A.R.V.I.S about ${profileName}...`}
                    className="flex-1 bg-black/40 border border-cyan-500/30 rounded-xl px-4 py-3 text-cyan-100 font-mono text-sm focus:border-teal-400 focus:outline-none placeholder:text-cyan-500/40 transition-colors shadow-inner"
                />
                <button
                    onClick={handleRagSubmit}
                    disabled={isRagLoading || !ragInput.trim()}
                    className="bg-cyan-950/50 border border-cyan-500/50 hover:border-teal-400 hover:text-teal-300 text-cyan-400 px-5 py-3 rounded-xl font-mono tracking-widest uppercase transition-all flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed group/ragbtn"
                >
                    {isRagLoading ? <Loader2 className="w-5 h-5 animate-spin text-teal-400" /> : <Send className="w-5 h-5 group-hover/ragbtn:scale-110 transition-transform" />}
                </button>
            </div>
        </div>
    );
};

const ChatInputBar = () => {
    const input = useChatStore(state => state.input);
    const setInput = useChatStore(state => state.setInput);
    const isLoading = useChatStore(state => state.isLoading);
    const setIsLoading = useChatStore(state => state.setIsLoading);
    const isListening = useChatStore(state => state.isListening);
    const setIsListening = useChatStore(state => state.setIsListening);
    const voiceEnabled = useChatStore(state => state.voiceEnabled);
    const setVoiceEnabled = useChatStore(state => state.setVoiceEnabled);
    const setMessages = useChatStore(state => state.setMessages);
    const setRagMessages = useChatStore(state => state.setRagMessages);
    const setRagInput = useChatStore(state => state.setRagInput);
    const setStreamingContent = useChatStore(state => state.setStreamingContent);
    const setHistory = useChatStore(state => state.setHistory);

    const recognitionRef = useRef<any>(null);

    useEffect(() => {
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (SpeechRecognition) {
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = false;
            recognitionRef.current.interimResults = false;
            recognitionRef.current.lang = 'tr-TR';

            recognitionRef.current.onresult = (event: any) => {
                const transcript = event.results[0][0].transcript;
                const currentInput = useChatStore.getState().input;
                setInput(currentInput + (currentInput ? ' ' : '') + transcript);
                setIsListening(false);
            };

            recognitionRef.current.onerror = () => setIsListening(false);
            recognitionRef.current.onend = () => setIsListening(false);
        }
    }, [setInput, setIsListening]);

    const toggleListening = () => {
        if (isListening) {
            recognitionRef.current?.stop();
            setIsListening(false);
        } else {
            recognitionRef.current?.start();
            setIsListening(true);
        }
    };

    const handleSearch = async () => {
        if (!input.trim() || isLoading) return;

        const userMessage: Message = {
            role: 'user',
            content: input.trim()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);
        setRagMessages([]);
        setRagInput('');

        try {
            const response = await searchPerson(input.trim());

            const assistantMessage: Message = {
                role: 'assistant',
                content: response.ai_response,
                profileData: response
            };

            setMessages(prev => [...prev, assistantMessage]);
            setStreamingContent('');

            // Background update history
            getSearchHistory().then(setHistory).catch(console.error);

        } catch (error: any) {
            setStreamingContent('');
            const errorMessage: Message = {
                role: 'assistant',
                content: `[ERROR] Analysis failed: ${error.response?.data?.detail || error.message || 'Unknown error'}. Please verify connection.`
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSearch();
        }
    };

    return (
        <motion.div
            initial={{ y: 100 }}
            animate={{ y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
            className="fixed bottom-10 left-0 w-full pl-[300px] pr-[280px] flex justify-center z-50 pointer-events-none"
        >
            <div className="pointer-events-auto w-full max-w-4xl glass-strong p-4 rounded-3xl flex gap-4 items-center border-2 border-cyan-500/30 shadow-[0_10px_40px_rgba(0,0,0,0.8)] relative overflow-hidden group hover:border-cyan-400/60 transition-all duration-500">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/10 to-cyan-500/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />

                <button
                    onClick={() => {
                        if (voiceEnabled) window.speechSynthesis.cancel();
                        setVoiceEnabled(!voiceEnabled);
                    }}
                    className={`p-3 rounded-xl border transition-all ${voiceEnabled ? 'border-cyan-400 bg-cyan-900/40 text-cyan-400 glow-cyan' : 'border-slate-700 bg-slate-900/40 text-slate-500'}`}
                    title={voiceEnabled ? "Mute JARVIS" : "Enable JARVIS Voice"}
                >
                    {voiceEnabled ? <Volume2 className="w-6 h-6" /> : <VolumeX className="w-6 h-6" />}
                </button>

                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="Enter name or username (use '/' to separate)..."
                    disabled={isLoading}
                    className="flex-1 input-jarvis h-14 rounded-2xl border-none shadow-none bg-black/20 focus:bg-black/40 placeholder:tracking-widest text-xl font-bold px-8 transition-all"
                />

                <button
                    onClick={toggleListening}
                    className={`relative w-14 h-14 rounded-xl flex items-center justify-center transition-all border-2 ${isListening ? 'border-red-500 bg-red-950/40 text-red-500' : 'border-cyan-500/50 bg-cyan-950/40 text-cyan-400 hover:border-cyan-300'}`}
                >
                    {isListening && (
                        <motion.div
                            animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
                            transition={{ repeat: Infinity, duration: 1.5 }}
                            className="absolute inset-0 bg-red-500/30 rounded-full"
                        />
                    )}
                    {isListening ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                </button>

                <button
                    onClick={handleSearch}
                    disabled={isLoading || !input.trim()}
                    className="btn-jarvis rounded-xl w-14 h-14 p-0 flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed group/btn hover:border-cyan-300 bg-cyan-950/40 border-2 border-cyan-500/50"
                >
                    {isLoading ? (
                        <Loader2 className="w-6 h-6 animate-spin text-cyan-300" />
                    ) : (
                        <Send className="w-6 h-6 text-cyan-400 group-hover/btn:text-white group-hover/btn:scale-110 transition-all drop-shadow-[0_0_8px_rgba(0,255,255,0.8)]" />
                    )}
                </button>
            </div>
        </motion.div>
    );
};

const LoadingIndicator = () => {
    const isLoading = useChatStore(state => state.isLoading);
    const streamingContent = useChatStore(state => state.streamingContent);

    if (!isLoading || !!streamingContent) return null;

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex justify-start w-full max-w-3xl"
        >
            <div className="glass-strong rounded-2xl p-8 w-full flex justify-center border-t-2 border-t-cyan-400 shadow-[0_0_30px_rgba(0,255,255,0.1)]">
                <LoadingAnimation />
            </div>
        </motion.div>
    );
};

const VoiceSynthesizer = () => {
    const messages = useChatStore(state => state.messages);
    const voiceEnabled = useChatStore(state => state.voiceEnabled);
    const isSpeaking = useChatStore(state => state.isSpeaking);
    const setIsSpeaking = useChatStore(state => state.setIsSpeaking);

    const speakResponse = React.useCallback((text: string) => {
        if (!text || !voiceEnabled) return;

        // Clean markdown for cleaner speech
        const cleanText = text.replace(/[*_#`\[\]()]/g, '').slice(0, 500);

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(cleanText);

        // JARVIS Protocol: Force high-quality British accent
        const voices = window.speechSynthesis.getVoices();
        const jarvisVoice = voices.find(v => v.name.includes('Google UK English Male') || v.lang === 'en-GB');
        if (jarvisVoice) utterance.voice = jarvisVoice;

        utterance.rate = 1.0;
        utterance.pitch = 0.9; // Deeper tone for JARVIS

        utterance.onstart = () => setIsSpeaking(true);
        utterance.onend = () => setIsSpeaking(false);
        utterance.onerror = () => setIsSpeaking(false);

        window.speechSynthesis.speak(utterance);
    }, [voiceEnabled, setIsSpeaking]);

    useEffect(() => {
        // Handle auto-speech for new assistant messages
        const lastMessage = messages[messages.length - 1];
        if (voiceEnabled && lastMessage?.role === 'assistant' && !isSpeaking) {
            speakResponse(lastMessage.content);
        }
    }, [messages, voiceEnabled, isSpeaking, speakResponse]);

    return null;
};

export default function ChatInterface() {
    const messages = useChatStore(state => state.messages);
    const setMessages = useChatStore(state => state.setMessages);
    const isLoading = useChatStore(state => state.isLoading);

    const addLiveStatus = useChatStore(state => state.addLiveStatus);
    const setStreamingContent = useChatStore(state => state.setStreamingContent);
    const addStreamingToken = useChatStore(state => state.addStreamingToken);
    const resetSearchState = useChatStore(state => state.resetSearchState);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let eventSource: EventSource | null = null;
        let intentionalClose = false;

        if (isLoading) {
            resetSearchState(); // Reset RAG and Live status
            eventSource = new EventSource(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/status/stream`);

            eventSource.onmessage = (event) => {
                const data = event.data as string;

                if (data === '[STREAM_START]') {
                    // AI streaming is about to begin — clear any previous content
                    setStreamingContent('');
                    return;
                }

                if (data === '[STREAM_END]') {
                    // AI streaming finished — no action needed, final response will replace
                    return;
                }

                if (data.startsWith('[STREAM] ')) {
                    const token = data.substring(9);
                    addStreamingToken(token);
                } else {
                    addLiveStatus(data);
                }
            };

            eventSource.onerror = () => {
                // Only close if not intentionally closed (prevents infinite reconnect loop)
                if (!intentionalClose && eventSource?.readyState !== EventSource.CLOSED) {
                    eventSource?.close();
                }
            };
        } else {
            setStreamingContent('');
        }

        return () => {
            intentionalClose = true;
            if (eventSource) eventSource.close();
        };
    }, [isLoading, resetSearchState, addStreamingToken, addLiveStatus, setStreamingContent]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);


    const handleApprove = async (messageIndex: number, profileToSave: SearchResponse) => {
        try {
            await saveProfile({
                name: profileToSave.name,
                github_url: profileToSave.github_url,
                instagram_url: profileToSave.instagram_url,
                twitter_url: profileToSave.twitter_url,
                linkedin_url: profileToSave.linkedin_url,
                spotify_url: profileToSave.spotify_url,
                tiktok_url: profileToSave.tiktok_url,
                snapchat_url: profileToSave.snapchat_url,
                tumblr_url: profileToSave.tumblr_url,
                youtube_url: profileToSave.youtube_url,
                reddit_url: profileToSave.reddit_url,
                facebook_url: profileToSave.facebook_url,
                tinder_mention: profileToSave.tinder_mention,
                bumble_mention: profileToSave.bumble_mention,
                phone_numbers: profileToSave.phone_numbers,
                description: profileToSave.description,
                additional_info: profileToSave.additional_info,
                similar_profiles: profileToSave.similar_profiles,
                cross_validation_issues: profileToSave.cross_validation_issues,
                network_connections: profileToSave.network_connections,
                email_addresses: profileToSave.email_addresses,
                data_breaches: profileToSave.data_breaches,
            });

            setMessages(prev => {
                const newMessages = [...prev];
                if (newMessages[messageIndex]) {
                    newMessages[messageIndex] = {
                        ...newMessages[messageIndex],
                        isSaved: true
                    };
                }
                return newMessages;
            });

        } catch (error: any) {
            const errorMessage: Message = {
                role: 'assistant',
                content: `[ERROR] Archive failure: ${error.response?.data?.detail || error.message}`
            };
            setMessages(prev => [...prev, errorMessage]);
        }
    };

    return (
        <div className="flex flex-col h-screen relative z-10 grid-background">
            {/* Background elements */}
            <div className="data-stream" />
            <div className="scan-line" />

            {/* Seamless HUD Header */}
            <motion.header
                initial={{ top: "40%", left: "50%", x: "-50%", y: "-50%", scale: 1.2 }}
                animate={{
                    top: messages.length === 0 ? "40%" : "2rem",
                    left: messages.length === 0 ? "50%" : "1.5rem",
                    x: messages.length === 0 ? "-50%" : "0%",
                    y: messages.length === 0 ? "-50%" : "0%",
                    scale: messages.length === 0 ? 1.2 : 0.85
                }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="fixed z-50 pointer-events-none origin-top-left"
            >
                <div className="glass-strong px-8 py-3.5 rounded-[2rem] flex items-center gap-6 border-cyan-400/40 shadow-[0_0_40px_rgba(0,255,255,0.1)] bg-cyan-950/40 backdrop-blur-md relative overflow-hidden group/logo">
                    {/* Animated shine line across the pill */}
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/10 to-transparent -translate-x-[150%] animate-[shimmer_3s_infinite]" />

                    <div className="relative flex items-center justify-center w-16 h-16 shrink-0 group-hover/logo:scale-110 transition-transform duration-700 ease-out">
                        {/* Outer Glow */}
                        <div className="absolute inset-0 bg-cyan-400/40 blur-xl rounded-full scale-75 group-hover/logo:scale-110 transition-transform duration-1000"></div>

                        {/* Outer Dotted Ring (Slow Reverse Spin) */}
                        <div className="absolute inset-[-4px] rounded-full border border-dashed border-cyan-500/30 animate-[spin_12s_linear_infinite_reverse]"></div>

                        {/* Middle Segmented Ring (Medium Forward Spin) */}
                        <div className="absolute inset-1 rounded-full border-[3px] border-transparent border-t-cyan-400 border-b-cyan-500/50 border-r-cyan-400/20 animate-[spin_8s_linear_infinite] shadow-[0_0_15px_rgba(0,255,255,0.4)]"></div>

                        {/* Inner Dashed Ring (Fast Reverse Spin) */}
                        <div className="absolute inset-3 rounded-full border-2 border-dotted border-cyan-300 animate-[spin_4s_linear_infinite_reverse]"></div>

                        {/* Core Glowing Orb */}
                        <div className="absolute inset-4 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-400 shadow-[0_0_20px_rgba(34,211,238,0.8)_inset] flex items-center justify-center overflow-hidden">
                            <div className="absolute inset-0 bg-cyan-300/30 blur-sm animate-pulse"></div>
                            <div className="w-2 h-2 bg-white rounded-full shadow-[0_0_10px_#fff]"></div>
                        </div>
                    </div>

                    <div className="flex flex-col justify-center">
                        <h1 className="text-4xl font-orbitron font-black tracking-[0.25em] leading-none mb-1 drop-shadow-[0_2px_10px_rgba(0,255,255,0.3)]">
                            <GlitchText
                                text="J.A.R.V.I.S"
                                interval={5000}
                                className="text-transparent bg-clip-text bg-gradient-to-r from-white via-cyan-100 to-cyan-400"
                            />
                        </h1>
                        <div className="flex items-center gap-2.5 mt-1">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500 shadow-[0_0_8px_rgba(0,255,255,0.8)]"></span>
                            </span>
                            <p className="text-cyan-300/90 text-[10px] font-bold uppercase tracking-[0.4em] glow-cyan font-mono">
                                Just A Rather Very Intelligent System
                            </p>
                        </div>
                    </div>
                </div>
            </motion.header>

            {/* History Sidebar */}
            <HistorySidebar />

            <VoiceSynthesizer />

            {/* Right Sidebar: Network Nodes or Live Status */}
            {(() => {
                // If loading, show live status stream
                if (isLoading) {
                    return <LiveStatusMonitor />;
                }

                // Find the latest assistant message with profileData
                const lastProfile = [...messages].reverse().find(m => m.role === 'assistant' && m.profileData)?.profileData;
                if (!lastProfile) return null;

                // Search fallback URL generator for platforms without found profiles
                const searchName = lastProfile.name || '';
                const encoded = encodeURIComponent(searchName);
                const searchUrls: Record<string, string> = {
                    'GitHub': `https://github.com/search?q=${encoded}&type=users`,
                    'Instagram': `https://www.instagram.com/explore/search/keyword/?q=${encoded}`,
                    'X (Twitter)': `https://x.com/search?q=${encoded}&f=user`,
                    'LinkedIn': `https://www.linkedin.com/search/results/people/?keywords=${encoded}`,
                    'Spotify': `https://open.spotify.com/search/${encoded}/profiles`,
                    'TikTok': `https://www.tiktok.com/search/user?q=${encoded}`,
                    'Snapchat': `https://www.snapchat.com/explore/${encoded}`,
                    'Tumblr': `https://www.tumblr.com/search/${encoded}`,
                    'YouTube': `https://www.youtube.com/results?search_query=${encoded}`,
                    'Reddit': `https://www.reddit.com/search/?q=${encoded}&type=user`,
                    'Facebook': `https://www.facebook.com/search/people/?q=${encoded}`,
                    'Pinterest': `https://www.pinterest.com/search/users/?q=${encoded}`,
                    'Medium': `https://medium.com/search?q=${encoded}`,
                    'Threads': `https://www.threads.net/search?q=${encoded}&filter=people`,
                    'Steam': `https://steamcommunity.com/search/users/#text=${encoded}`,
                };

                const allPlatforms = [
                    { icon: Github, urls: lastProfile.github_url, label: 'GitHub', brandStyles: 'border-gray-500/40 bg-gray-900/50 hover:bg-gray-800/80 hover:border-gray-400 text-gray-300 shadow-[0_4px_15px_rgba(156,163,175,0.15)]' },
                    { icon: Instagram, urls: lastProfile.instagram_url, label: 'Instagram', brandStyles: 'border-pink-500/40 bg-fuchsia-950/40 hover:bg-fuchsia-900/60 hover:border-pink-400 text-pink-400 shadow-[0_4px_15px_rgba(236,72,153,0.15)]' },
                    { icon: Twitter, urls: lastProfile.twitter_url, label: 'X (Twitter)', brandStyles: 'border-slate-500/40 bg-slate-900/50 hover:bg-slate-800/80 hover:border-slate-300 text-slate-300 shadow-[0_4px_15px_rgba(148,163,184,0.15)]' },
                    { icon: Linkedin, urls: lastProfile.linkedin_url, label: 'LinkedIn', brandStyles: 'border-blue-500/40 bg-blue-950/50 hover:bg-blue-900/60 hover:border-blue-400 text-blue-400 shadow-[0_4px_15px_rgba(59,130,246,0.15)]' },
                    { icon: SpotifyIcon, urls: lastProfile.spotify_url, label: 'Spotify', brandStyles: 'border-green-500/40 bg-emerald-950/40 hover:bg-emerald-900/60 hover:border-green-400 text-green-400 shadow-[0_4px_15px_rgba(34,197,94,0.15)]' },
                    { icon: TikTokIcon, urls: lastProfile.tiktok_url, label: 'TikTok', brandStyles: 'border-rose-500/40 bg-rose-950/40 hover:bg-rose-900/60 hover:border-rose-400 text-rose-400 shadow-[0_4px_15px_rgba(244,63,94,0.15)]' },
                    { icon: SnapchatIcon, urls: lastProfile.snapchat_url, label: 'Snapchat', brandStyles: 'border-yellow-500/40 bg-yellow-950/40 hover:bg-yellow-900/60 hover:border-yellow-400 text-yellow-400 shadow-[0_4px_15px_rgba(250,204,21,0.15)]' },
                    { icon: TumblrIcon, urls: lastProfile.tumblr_url, label: 'Tumblr', brandStyles: 'border-indigo-500/40 bg-indigo-950/40 hover:bg-indigo-900/60 hover:border-indigo-400 text-indigo-400 shadow-[0_4px_15px_rgba(99,102,241,0.15)]' },
                    { icon: YoutubeIcon, urls: lastProfile.youtube_url, label: 'YouTube', brandStyles: 'border-red-500/40 bg-red-950/40 hover:bg-red-900/60 hover:border-red-400 text-red-400 shadow-[0_4px_15px_rgba(239,68,68,0.15)]' },
                    { icon: RedditIcon, urls: lastProfile.reddit_url, label: 'Reddit', brandStyles: 'border-orange-500/40 bg-orange-950/40 hover:bg-orange-900/60 hover:border-orange-400 text-orange-400 shadow-[0_4px_15px_rgba(249,115,22,0.15)]' },
                    { icon: FacebookIcon, urls: lastProfile.facebook_url, label: 'Facebook', brandStyles: 'border-blue-600/40 bg-blue-950/40 hover:bg-blue-900/60 hover:border-blue-500 text-blue-500 shadow-[0_4px_15px_rgba(59,130,246,0.15)]' },
                    { icon: PinterestIcon, urls: lastProfile.pinterest_url, label: 'Pinterest', brandStyles: 'border-red-600/40 bg-red-950/40 hover:bg-red-900/60 hover:border-red-500 text-red-500 shadow-[0_4px_15px_rgba(220,38,38,0.15)]' },
                    { icon: MediumIcon, urls: lastProfile.medium_url, label: 'Medium', brandStyles: 'border-gray-400/40 bg-gray-950/50 hover:bg-gray-800/80 hover:border-gray-300 text-gray-200 shadow-[0_4px_15px_rgba(229,231,235,0.15)]' },
                    { icon: ThreadsIcon, urls: lastProfile.threads_url, label: 'Threads', brandStyles: 'border-gray-500/40 bg-gray-900/50 hover:bg-gray-800/80 hover:border-gray-400 text-gray-300 shadow-[0_4px_15px_rgba(156,163,175,0.15)]' },
                    { icon: SteamIcon, urls: lastProfile.steam_url, label: 'Steam', brandStyles: 'border-blue-800/40 bg-blue-950/50 hover:bg-blue-900/60 hover:border-blue-600 text-blue-400 shadow-[0_4px_15px_rgba(30,64,175,0.15)]' },
                ];

                // Separate: found profiles vs search fallbacks
                const foundEntries = allPlatforms.filter(e => e.urls);
                const searchEntries = allPlatforms.filter(e => !e.urls && searchUrls[e.label]);

                // Mention-type entries (Tinder, Bumble, Discord)
                const mentionEntries = [
                    { icon: TinderIcon, urls: lastProfile.tinder_mention, label: 'Tinder', isMention: true, brandStyles: 'border-orange-500/40 bg-orange-950/40 hover:bg-orange-900/60 hover:border-orange-400 text-orange-400 shadow-[0_4px_15px_rgba(249,115,22,0.15)]' },
                    { icon: BumbleIcon, urls: lastProfile.bumble_mention, label: 'Bumble', isMention: true, brandStyles: 'border-amber-500/40 bg-amber-950/40 hover:bg-amber-900/60 hover:border-amber-400 text-amber-400 shadow-[0_4px_15px_rgba(245,158,11,0.15)]' },
                    { icon: DiscordIcon, urls: lastProfile.discord_mention, label: 'Discord', isMention: true, brandStyles: 'border-violet-500/40 bg-violet-950/40 hover:bg-violet-900/60 hover:border-violet-400 text-violet-400 shadow-[0_4px_15px_rgba(139,92,246,0.15)]' },
                ].filter(e => e.urls);

                const socialEntries: any[] = [...foundEntries, ...mentionEntries];

                // Add phone numbers if found
                if (lastProfile.phone_numbers && lastProfile.phone_numbers.length > 0) {
                    socialEntries.push({
                        icon: PhoneIcon,
                        urls: lastProfile.phone_numbers.join(', '),
                        label: 'Phone',
                        brandStyles: 'border-emerald-500/40 bg-emerald-950/40 hover:bg-emerald-900/60 hover:border-emerald-400 text-emerald-400 shadow-[0_4px_15px_rgba(52,211,153,0.15)]',
                    });
                }

                return (
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8, delay: 0.3, ease: 'easeOut' }}
                        className="fixed z-40 right-6 top-6 w-60 glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden"
                    >
                        <div className="p-2.5 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_5s_infinite]" />
                            <Globe className="w-4 h-4 text-cyan-400" />
                            <ScrambleText text="Network Nodes" className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan" />
                            <span className="ml-auto text-[8px] font-mono bg-cyan-400/10 text-cyan-400 px-1.5 py-0.5 rounded-full border border-cyan-500/30">{socialEntries.length + searchEntries.length}</span>
                        </div>
                        <div className="p-2 space-y-1.5 overflow-y-auto max-h-[80vh] custom-scrollbar">
                            <AnimatePresence>
                                {/* Empty state when no social profiles found */}
                                {socialEntries.length === 0 && (
                                    <motion.div
                                        key="no-profiles"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="flex flex-col items-center gap-2 py-4 opacity-50"
                                    >
                                        <Globe className="w-5 h-5 text-cyan-500" />
                                        <span className="text-[9px] font-mono text-cyan-500/60 text-center">No social profiles detected</span>
                                    </motion.div>
                                )}
                                {/* Network Nodes Section */}
                                {socialEntries.flatMap(({ icon: Icon, urls, label, brandStyles, isMention }: any) => {
                                    if (!urls) return [];

                                    // Phone numbers & mentions: single non-link entry
                                    if (label === 'Phone' || isMention) {
                                        return [(
                                            <motion.div
                                                key={label}
                                                initial={{ opacity: 0, x: 20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                className={`flex items-center gap-2 p-2 rounded-xl border transition-all ${brandStyles}`}
                                            >
                                                <Icon className="w-4 h-4 shrink-0" />
                                                <div className="flex flex-col overflow-hidden">
                                                    <div className="flex items-center gap-1">
                                                        <span className="text-[11px] text-white font-bold font-mono tracking-wider drop-shadow-sm">{label}</span>
                                                        {isMention && <span className="text-[7px] font-mono bg-white/10 px-1 rounded">MENTION</span>}
                                                    </div>
                                                    <span className="text-[8px] opacity-60 font-mono truncate">{typeof urls === 'string' ? urls.substring(0, 40) : urls}</span>
                                                </div>
                                            </motion.div>
                                        )];
                                    }

                                    // Standard clickable URL entries (only valid http/https URLs)
                                    const parsedUrls = urls.split(',').map((u: string) => u.trim()).filter((u: string) => {
                                        try { const p = new URL(u); return p.protocol === 'http:' || p.protocol === 'https:'; }
                                        catch { return false; }
                                    });
                                    if (parsedUrls.length === 0) return [];
                                    return parsedUrls.map((singleUrl: string, idx: number) => {
                                        const username = singleUrl.replace(/\/+$/, '').split('/').pop() || '';
                                        const displayLabel = parsedUrls.length > 1 ? `@${username}` : label;
                                        return (
                                            <motion.a
                                                key={`${label}-${idx}`}
                                                href={singleUrl}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                initial={{ opacity: 0, x: 20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: idx * 0.05 }}
                                                className={`flex items-center gap-2 p-2 rounded-xl border transition-all group/link ${brandStyles}`}
                                                whileHover={{ x: -3, scale: 1.02 }}
                                                whileTap={{ scale: 0.98 }}
                                            >
                                                <Icon className="w-4 h-4 transition-colors group-hover/link:text-white shrink-0" />
                                                <span className="text-[11px] text-white font-bold font-mono tracking-wider drop-shadow-sm truncate">{displayLabel}</span>
                                            </motion.a>
                                        );
                                    });
                                })}

                                {/* Search Fallback Section — platforms without found profiles */}
                                {searchEntries.length > 0 && (
                                    <motion.div
                                        key="search-fallbacks"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="flex flex-col gap-1.5"
                                    >
                                        <div className="pt-2 pb-1 border-t border-cyan-500/10 mt-1">
                                            <div className="flex items-center gap-2 px-1">
                                                <Search className="w-3 h-3 text-cyan-500/50" />
                                                <span className="text-[8px] font-bold font-mono tracking-widest text-cyan-500/50 uppercase">Search on Platform</span>
                                            </div>
                                        </div>
                                        {searchEntries.map(({ icon: Icon, label, brandStyles }: any, idx: number) => (
                                            <motion.a
                                                key={`search-${label}`}
                                                href={searchUrls[label]}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                initial={{ opacity: 0, x: 10 }}
                                                animate={{ opacity: 0.7, x: 0 }}
                                                transition={{ delay: idx * 0.03 }}
                                                className="flex items-center gap-2 p-1.5 rounded-lg border border-white/10 bg-white/[0.03] hover:bg-white/[0.08] hover:opacity-100 hover:border-cyan-500/30 transition-all group/search"
                                                whileHover={{ x: -2, scale: 1.02 }}
                                            >
                                                <Icon className="w-3.5 h-3.5 opacity-50 group-hover/search:opacity-80 shrink-0" />
                                                <span className="text-[10px] text-white/50 font-mono tracking-wider truncate group-hover/search:text-white/70">{label}</span>
                                                <span className="text-[7px] font-mono bg-cyan-500/10 text-cyan-400/50 px-1.5 py-0.5 rounded ml-auto shrink-0 group-hover/search:bg-cyan-500/20 group-hover/search:text-cyan-400/80">SEARCH</span>
                                            </motion.a>
                                        ))}
                                    </motion.div>
                                )}

                                {/* Intelligence Sources Section */}
                                {lastProfile.sources && lastProfile.sources.length > 0 && (
                                    <motion.div
                                        key="intelligence-sources"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        className="flex flex-col gap-2"
                                    >
                                        <div className="pt-2 pb-1 border-t border-cyan-500/20 mt-2">
                                            <div className="flex items-center gap-2 px-1">
                                                <TerminalSquare className="w-3.5 h-3.5 text-cyan-400" />
                                                <ScrambleText text="Intelligence Sources" className="text-[9px] font-bold font-mono tracking-widest text-cyan-500/80 uppercase" />
                                            </div>
                                        </div>
                                        {lastProfile.sources.slice(0, 4).map((source, idx) => (
                                            <motion.a
                                                key={`source-${idx}`}
                                                href={source.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                initial={{ opacity: 0, x: 20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: 0.2 + idx * 0.05 }}
                                                className="flex flex-col gap-0.5 p-2.5 rounded-xl border border-cyan-500/20 bg-cyan-950/40 hover:bg-cyan-900/60 hover:border-cyan-400/50 transition-all group/source"
                                                whileHover={{ x: -3, scale: 1.02 }}
                                                whileTap={{ scale: 0.98 }}
                                            >
                                                <div className="flex items-center gap-1.5 overflow-hidden">
                                                    <Globe className="w-3 h-3 text-cyan-500/60 group-hover/source:text-cyan-400" />
                                                    <span className="text-[10px] text-cyan-100/90 font-bold font-mono truncate">{source.title}</span>
                                                </div>
                                                <span className="text-[8px] text-cyan-500/50 truncate pl-4 font-mono">{(() => { try { return new URL(source.url).hostname; } catch { return source.url.substring(0, 30); } })()}</span>
                                            </motion.a>
                                        ))}
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </motion.div>
                );
            })()}

            {/* Floating Atmospheric Widget (Between Chat and Right Sidebar) */}
            {(() => {
                const lastProfile = [...messages].reverse().find(m => m.role === 'assistant' && m.profileData)?.profileData;
                if (!lastProfile || !lastProfile.weather_info) return null;

                const weather = lastProfile.weather_info;
                const isSunny = weather && (weather.temperature > 20 || weather.description.toLowerCase().includes('clear') || weather.description.toLowerCase().includes('sunny'));

                return (
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8, delay: 0.3, ease: 'easeOut' }}
                        className="fixed z-40 right-[17rem] top-6 w-56 glass-strong rounded-[1.5rem] border border-cyan-500/20 bg-cyan-950/20 backdrop-blur-md shadow-[0_0_20px_rgba(0,255,255,0.05)] flex flex-col overflow-hidden pointer-events-auto group/weather"
                    >
                        {/* Weather Header */}
                        <div className="p-3 border-b border-cyan-500/20 bg-cyan-900/40 flex items-center gap-2 relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-[shimmer_5s_infinite]" />
                            <Cloud className="w-4 h-4 text-cyan-400" />
                            <span className="text-[10px] font-bold font-mono tracking-widest text-cyan-300 uppercase glow-cyan">Weather Scan</span>
                        </div>

                        <div className="p-3 flex flex-col gap-3">
                            {/* Decorative scan line */}
                            <div className="absolute top-0 left-0 w-full h-0.5 bg-cyan-400/30 animate-[scan_3s_linear_infinite]" />

                            {/* Weather Icon / Environment Display */}
                            <div className="relative h-24 w-full rounded-xl bg-gradient-to-b from-black/40 to-cyan-900/20 border border-white/5 flex items-center justify-center overflow-hidden">
                                {isSunny ? (
                                    <div className="relative">
                                        <motion.div
                                            animate={{ rotate: 360 }}
                                            transition={{ repeat: Infinity, duration: 20, ease: "linear" }}
                                            className="absolute inset-0 bg-yellow-400/20 blur-2xl rounded-full scale-125"
                                        />
                                        <Sun className="w-10 h-10 text-yellow-400 drop-shadow-[0_0_12px_rgba(250,204,21,0.7)] relative z-10" />
                                    </div>
                                ) : (
                                    <div className="relative">
                                        <motion.div
                                            animate={{ x: [-10, 10, -10] }}
                                            transition={{ repeat: Infinity, duration: 8, ease: "easeInOut" }}
                                            className="absolute -top-2 -left-4 opacity-50"
                                        >
                                            <Cloud className="w-10 h-10 text-slate-400" />
                                        </motion.div>
                                        <Cloud className="w-14 h-14 text-slate-300 drop-shadow-[0_0_10px_rgba(203,213,225,0.5)] relative z-10" />
                                    </div>
                                )}

                                {/* Temperature Overlay */}
                                {weather && (
                                    <div className="absolute bottom-2 right-3 flex items-center gap-1">
                                        <Thermometer className="w-3 h-3 text-cyan-400" />
                                        <span className="text-sm font-orbitron font-black text-white glow-white">{weather.temperature}°C</span>
                                    </div>
                                )}
                            </div>

                            {/* Location & Status */}
                            <div className="space-y-1">
                                <div className="flex items-center gap-1.5 overflow-hidden">
                                    <MapPin className="w-3 h-3 text-cyan-400 shrink-0" />
                                    <span className="text-[10px] font-black font-orbitron tracking-widest text-white uppercase truncate drop-shadow-sm">
                                        {lastProfile.location_city || "Unknown Node"}
                                    </span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                    <div className={`w-1 h-1 rounded-full ${weather ? 'bg-cyan-400 animate-pulse' : 'bg-red-500'}`} />
                                    <span className={`text-[8px] font-bold font-mono tracking-widest uppercase ${weather ? 'text-cyan-400 glow-cyan' : 'text-red-400'}`}>
                                        {weather?.description || "OFFLINE"}
                                    </span>
                                </div>
                            </div>

                            {/* Wind speed if available */}
                            {weather?.wind_speed && (
                                <div className="pt-2 border-t border-cyan-500/10 flex justify-between items-center opacity-70">
                                    <span className="text-[9px] font-mono text-cyan-500 uppercase tracking-tighter">Atmospheric Flow</span>
                                    <div className="flex items-center gap-1">
                                        <Wind className="w-3.5 h-3.5 text-cyan-300" />
                                        <span className="text-[10px] font-mono font-bold text-white">{weather.wind_speed} <span className="text-[8px]">km/h</span></span>
                                    </div>
                                </div>
                            )}

                            {/* Hover effect highlight */}
                            <div className="absolute inset-0 border-2 border-transparent group-hover/weather:border-cyan-400/20 rounded-2xl transition-all duration-500" />
                        </div>
                    </motion.div>
                );
            })()}

            {/* Social Gauge Widget */}
            {(() => {
                const lastProfile = [...messages].reverse().find(m => m.role === 'assistant' && m.profileData)?.profileData;
                if (!lastProfile || typeof lastProfile.social_media_score === 'undefined') return null;

                return (
                    <SocialGauge
                        score={lastProfile.social_media_score}
                        lastActive={lastProfile.last_activity_summary}
                        breakdown={lastProfile.social_media_score_breakdown}
                        platformActivity={lastProfile.platform_activity}
                    />
                );
            })()}

            {/* Sentiment Psychological Profiler Widget (Under Social Gauge) */}
            {(() => {
                const lastProfile = [...messages].reverse().find(m => m.role === 'assistant' && m.profileData)?.profileData;
                if (!lastProfile || !lastProfile.sentiment_analysis) return null;

                // Adjust positioning dynamically (assuming SocialGauge takes up some space, we place this right below it)
                return (
                    <motion.div
                        initial={{ opacity: 0, x: -50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8, delay: 0.6, ease: 'easeOut' }}
                        className="fixed z-40 left-6 bottom-16 w-64 pointer-events-auto"
                    >
                        <SentimentGauge data={lastProfile.sentiment_analysis as any} />
                    </motion.div>
                );
            })()}

            {/* Messages Area */}
            <motion.div
                initial={{ paddingTop: "52vh", paddingBottom: "8rem" }}
                animate={{
                    paddingTop: messages.length === 0 ? "52vh" : "8rem",
                    paddingBottom: messages.length === 0 ? "8rem" : "9rem"
                }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="flex-1 overflow-y-auto px-4 scroll-smooth"
            >
                <div className="max-w-4xl mx-auto space-y-8">
                    <AnimatePresence initial={false}>
                        {messages.map((message, index) => (
                            <motion.div
                                key={index}
                                initial={{ opacity: 0, y: 20, scale: 0.98 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                transition={{ duration: 0.4, ease: "easeOut" }}
                                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                {message.role === 'user' ? (
                                    <div className="message-bubble message-user max-w-xl text-white font-medium shadow-[0_4px_15px_rgba(0,0,0,0.5)] border-white/20">
                                        {message.content}
                                    </div>
                                ) : (
                                    <div className="w-full max-w-3xl space-y-6">
                                        <div className="message-bubble message-ai text-white font-mono text-[15px] leading-normal tracking-wide shadow-lg border-l-4 border-cyan-400">
                                            <div className="flex items-center gap-2 mb-3 text-cyan-400 font-bold pb-2 border-b border-cyan-500/30">
                                                <TerminalSquare className="w-5 h-5 glow-cyan" />
                                                <span className="text-sm uppercase tracking-[0.2em] glow-cyan">System Response</span>
                                            </div>
                                            <ReactMarkdown
                                                components={{
                                                    strong: ({ children, ...props }) => {
                                                        // Simple static hash to ensure the same header gets the same color consistently
                                                        const getHash = (str: string) => {
                                                            let hash = 0;
                                                            for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
                                                            return Math.abs(hash);
                                                        };

                                                        const textContent = Array.isArray(children) ? children.join('') : String(children);
                                                        const colors = [
                                                            'text-red-400 drop-shadow-[0_0_8px_rgba(248,113,113,0.8)]',
                                                            'text-green-400 drop-shadow-[0_0_8px_rgba(74,222,128,0.8)]',
                                                            'text-yellow-400 drop-shadow-[0_0_8px_rgba(250,204,21,0.8)]',
                                                            'text-blue-400 drop-shadow-[0_0_8px_rgba(96,165,250,0.8)]',
                                                            'text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.8)]'
                                                        ];
                                                        const colorClass = colors[getHash(textContent) % colors.length];

                                                        return (
                                                            <strong className={`${colorClass} font-black tracking-wider uppercase`} {...props}>
                                                                {children}
                                                            </strong>
                                                        );
                                                    },
                                                    p: ({ children, ...props }) => {
                                                        const isImageContainer = React.Children.toArray(children).some(
                                                            (child) => React.isValidElement(child) && (child as React.ReactElement<any>).props.node?.tagName === 'img'
                                                        );
                                                        if (isImageContainer) {
                                                            return <div className="flex flex-wrap gap-4 mb-5 items-center justify-start">{children}</div>;
                                                        }
                                                        return <p className="leading-normal text-gray-200 mb-2 last:mb-0" {...props}>{children}</p>;
                                                    },
                                                    ul: ({ ...props }) => <ul className="list-none space-y-1 mb-2" {...props} />,
                                                    li: ({ ...props }) => (
                                                        <li className="flex gap-2">
                                                            <span className="text-cyan-500 mt-0.5">▹</span>
                                                            <span className="text-gray-300" {...props} />
                                                        </li>
                                                    ),
                                                    img: ({ ...props }) => {
                                                        const src = typeof props.src === 'string' ? props.src : '';
                                                        const isWikiLogo = src.includes('wikipedia') && src.endsWith('.png');
                                                        if (isWikiLogo) return null; // Filter out rogue wikipedia textual logos
                                                        return (
                                                            <span className="inline-block shrink-0 rounded-2xl overflow-hidden border-2 border-cyan-500/50 w-32 h-32 sm:w-40 sm:h-40 shadow-[0_0_20px_rgba(0,255,255,0.25)] ring-1 ring-cyan-300/20 transition-transform hover:scale-105">
                                                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                                                <img
                                                                    className="w-full h-full object-cover object-top"
                                                                    {...props}
                                                                    alt={props.alt || "Profile Image"}
                                                                    onLoad={(e) => {
                                                                        const target = e.target as HTMLImageElement;
                                                                        // unavatar.io default generic fallback images usually render at 400x400 dimension exactly
                                                                        if (target.src.includes('unavatar.io') && target.naturalWidth === 400 && target.naturalHeight === 400) {
                                                                            const spanWrapper = target.parentElement;
                                                                            if (spanWrapper) spanWrapper.style.display = 'none';
                                                                            target.style.display = 'none';
                                                                        }
                                                                    }}
                                                                    onError={(e) => {
                                                                        const target = e.target as HTMLImageElement;
                                                                        const spanWrapper = target.parentElement;
                                                                        if (spanWrapper) {
                                                                            spanWrapper.style.display = 'none';
                                                                        }
                                                                        target.style.display = 'none';
                                                                    }}
                                                                />
                                                            </span>
                                                        );
                                                    },
                                                    a: ({ ...props }) => <a className="text-blue-400 hover:text-cyan-300 underline underline-offset-4 transition-colors" target="_blank" rel="noopener noreferrer" {...props} />
                                                }}
                                            >
                                                {message.content}
                                            </ReactMarkdown>
                                        </div>
                                        {message.profileData && (
                                            <div className="mt-4">
                                                <ProfileCard profile={message.profileData} />
                                                {message.profileData.version_history && message.profileData.version_history.snapshot_count >= 2 && (
                                                    <VersionHistory report={message.profileData.version_history} />
                                                )}
                                                {message.profileData.face_match_results && message.profileData.face_match_results.total_comparisons > 0 && (
                                                    <FaceMatch report={message.profileData.face_match_results} />
                                                )}
                                                <div className="mt-3 flex flex-col md:flex-row items-end justify-between gap-3 text-right">
                                                    <span className="text-gray-400 italic text-xs max-w-sm">
                                                        Aradığınız sonuç doğruysa daha sonrası için veritabanına kaydetmeniz erişim açısından daha iyi olur.
                                                    </span>
                                                    {!message.isSaved ? (
                                                        <button
                                                            onClick={() => handleApprove(index, message.profileData!)}
                                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-900/40 hover:border-cyan-400 transition-colors shadow-[0_0_10px_rgba(0,255,255,0.1)] shrink-0"
                                                        >
                                                            <Save className="w-4 h-4" />
                                                            <span className="text-sm font-semibold tracking-wide">Kaydet</span>
                                                        </button>
                                                    ) : (
                                                        <div className="flex items-center gap-1.5 px-3 py-1.5 text-green-400 font-medium shrink-0">
                                                            <CheckCircle className="w-5 h-5" />
                                                            <span className="text-sm">DB'ye Kaydedildi</span>
                                                        </div>
                                                    )}
                                                </div>

                                                {/* RAG Interactive Chat Mode (Only for the latest profile) */}
                                                {index === messages.length - 1 && (
                                                    <RagInteractionPanel profileName={message.profileData.name} />
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </motion.div>
                        ))}

                        {/* Live Streaming Message Bubble */}
                        <StreamingMessageBubble />
                    </AnimatePresence>

                    <LoadingIndicator />

                    <div id="messages-end" ref={messagesEndRef} className="h-4" />
                </div>
            </motion.div>

            {/* Futuristic Floating Input Bar */}
            <ChatInputBar />
        </div>
    );
}
