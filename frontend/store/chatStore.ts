import { create } from 'zustand';
import { Message, SearchHistoryItem } from '@/types/profile';

interface ChatState {
    // Core Data
    messages: Message[];
    input: string;
    isLoading: boolean;
    history: SearchHistoryItem[];

    // UI/UX State
    isListening: boolean;
    voiceEnabled: boolean;
    isSpeaking: boolean;

    // Streaming Status
    liveStatus: string[];
    streamingContent: string;

    // RAG Chat State
    ragMessages: { role: 'user' | 'assistant', content: string }[];
    ragInput: string;
    isRagLoading: boolean;
    streamingRagContent: string;

    // Actions
    setMessages: (updater: Message[] | ((prev: Message[]) => Message[])) => void;
    setInput: (input: string) => void;
    setIsLoading: (isLoading: boolean) => void;
    setHistory: (updater: SearchHistoryItem[] | ((prev: SearchHistoryItem[]) => SearchHistoryItem[])) => void;

    setIsListening: (isListening: boolean) => void;
    setVoiceEnabled: (voiceEnabled: boolean) => void;
    setIsSpeaking: (isSpeaking: boolean) => void;

    setLiveStatus: (updater: string[] | ((prev: string[]) => string[])) => void;
    setStreamingContent: (updater: string | ((prev: string) => string)) => void;
    addLiveStatus: (status: string) => void;
    addStreamingToken: (token: string) => void;

    setRagMessages: (updater: any[] | ((prev: any[]) => any[])) => void;
    setRagInput: (input: string) => void;
    setIsRagLoading: (isLoading: boolean) => void;
    setStreamingRagContent: (content: string) => void;

    // Reset utility
    resetSearchState: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
    // Initial Values
    messages: [],
    input: '',
    isLoading: false,
    history: [],

    isListening: false,
    voiceEnabled: false,
    isSpeaking: false,

    liveStatus: [],
    streamingContent: '',

    ragMessages: [],
    ragInput: '',
    isRagLoading: false,
    streamingRagContent: '',

    // Simple Setters (Allows both direct value and callback updates)
    setMessages: (updater) => set((state) => ({ messages: typeof updater === 'function' ? updater(state.messages) : updater })),
    setInput: (input) => set({ input }),
    setIsLoading: (isLoading) => set({ isLoading }),
    setHistory: (updater) => set((state) => ({ history: typeof updater === 'function' ? updater(state.history) : updater })),

    setIsListening: (isListening) => set({ isListening }),
    setVoiceEnabled: (voiceEnabled) => set({ voiceEnabled }),
    setIsSpeaking: (isSpeaking) => set({ isSpeaking }),

    setLiveStatus: (updater) => set((state) => ({ liveStatus: typeof updater === 'function' ? updater(state.liveStatus) : updater })),
    setStreamingContent: (updater) => set((state) => ({ streamingContent: typeof updater === 'function' ? updater(state.streamingContent) : updater })),

    // Complex state updaters
    addLiveStatus: (status) => set((state) => {
        const newStatus = [...state.liveStatus, status].slice(-12);
        return { liveStatus: newStatus };
    }),

    addStreamingToken: (token) => set((state) => ({
        streamingContent: state.streamingContent + token.replace(/\\n/g, '\n')
    })),

    setRagMessages: (updater) => set((state) => ({ ragMessages: typeof updater === 'function' ? updater(state.ragMessages) : updater })),
    setRagInput: (ragInput) => set({ ragInput }),
    setIsRagLoading: (isRagLoading) => set({ isRagLoading }),
    setStreamingRagContent: (streamingRagContent) => set({ streamingRagContent }),

    resetSearchState: () => set({
        ragMessages: [],
        ragInput: '',
        streamingContent: '',
        liveStatus: ["Establishing secure link..."]
    })
}));
