import { create } from 'zustand';
import { Message, SearchHistoryItem, RagMessage, AgentMessage, UserMemory, WatchTarget, PluginInfo, SystemAction } from '@/types/profile';

export type SidePanel = 'history' | 'memory' | 'watch' | 'plugins' | 'system' | 'health' | null;

interface ChatState {
    // Core Data
    messages: Message[];
    input: string;
    isLoading: boolean;
    history: SearchHistoryItem[];

    // UI/UX State

    // Streaming Status
    liveStatus: string[];
    streamingContent: string;

    // RAG Chat State
    ragMessages: RagMessage[];
    ragInput: string;
    isRagLoading: boolean;
    streamingRagContent: string;

    // Agent Mode
    isAgentMode: boolean;
    agentMessages: AgentMessage[];
    isAgentLoading: boolean;
    streamingAgentContent: string;

    // Side Panels
    activeSidePanel: SidePanel;

    // Search Depth
    searchDepth: number;

    // Feature State
    activeWatches: WatchTarget[];
    userMemories: UserMemory[];
    plugins: PluginInfo[];
    pendingActions: SystemAction[];

    // Actions
    setMessages: (updater: Message[] | ((prev: Message[]) => Message[])) => void;
    setInput: (input: string) => void;
    setIsLoading: (isLoading: boolean) => void;
    setHistory: (updater: SearchHistoryItem[] | ((prev: SearchHistoryItem[]) => SearchHistoryItem[])) => void;

    setLiveStatus: (updater: string[] | ((prev: string[]) => string[])) => void;
    setStreamingContent: (updater: string | ((prev: string) => string)) => void;
    addLiveStatus: (status: string) => void;
    addStreamingToken: (token: string) => void;

    setRagMessages: (updater: RagMessage[] | ((prev: RagMessage[]) => RagMessage[])) => void;
    setRagInput: (input: string) => void;
    setIsRagLoading: (isLoading: boolean) => void;
    setStreamingRagContent: (content: string) => void;

    // Agent actions
    setAgentMode: (on: boolean) => void;
    setAgentMessages: (updater: AgentMessage[] | ((prev: AgentMessage[]) => AgentMessage[])) => void;
    setIsAgentLoading: (v: boolean) => void;
    setStreamingAgentContent: (v: string) => void;

    // Search Depth
    setSearchDepth: (depth: number) => void;

    // Panel actions
    setActiveSidePanel: (panel: SidePanel) => void;

    // Feature actions
    setActiveWatches: (watches: WatchTarget[]) => void;
    setUserMemories: (memories: UserMemory[]) => void;
    setPlugins: (plugins: PluginInfo[]) => void;
    setPendingActions: (actions: SystemAction[]) => void;

    // Reset utility
    resetSearchState: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
    // Initial Values
    messages: [],
    input: '',
    isLoading: false,
    history: [],

    liveStatus: [],
    streamingContent: '',

    ragMessages: [],
    ragInput: '',
    isRagLoading: false,
    streamingRagContent: '',

    isAgentMode: false,
    agentMessages: [],
    isAgentLoading: false,
    streamingAgentContent: '',

    activeSidePanel: 'history',

    searchDepth: 5,

    activeWatches: [],
    userMemories: [],
    plugins: [],
    pendingActions: [],

    // Simple Setters (Allows both direct value and callback updates)
    setMessages: (updater) => set((state) => ({ messages: typeof updater === 'function' ? updater(state.messages) : updater })),
    setInput: (input) => set({ input }),
    setIsLoading: (isLoading) => set({ isLoading }),
    setHistory: (updater) => set((state) => ({ history: typeof updater === 'function' ? updater(state.history) : updater })),

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

    setRagMessages: (updater: RagMessage[] | ((prev: RagMessage[]) => RagMessage[])) => set((state) => ({ ragMessages: typeof updater === 'function' ? updater(state.ragMessages) : updater })),
    setRagInput: (ragInput) => set({ ragInput }),
    setIsRagLoading: (isRagLoading) => set({ isRagLoading }),
    setStreamingRagContent: (streamingRagContent) => set({ streamingRagContent }),

    // Agent
    setAgentMode: (isAgentMode) => set({ isAgentMode }),
    setAgentMessages: (updater) => set((state) => ({ agentMessages: typeof updater === 'function' ? updater(state.agentMessages) : updater })),
    setIsAgentLoading: (isAgentLoading) => set({ isAgentLoading }),
    setStreamingAgentContent: (streamingAgentContent) => set({ streamingAgentContent }),

    // Search Depth
    setSearchDepth: (searchDepth) => set({ searchDepth }),

    // Panels
    setActiveSidePanel: (activeSidePanel) => set({ activeSidePanel }),

    // Features
    setActiveWatches: (activeWatches) => set({ activeWatches }),
    setUserMemories: (userMemories) => set({ userMemories }),
    setPlugins: (plugins) => set({ plugins }),
    setPendingActions: (pendingActions) => set({ pendingActions }),

    resetSearchState: () => set({
        ragMessages: [],
        ragInput: '',
        streamingContent: '',
        liveStatus: ["Establishing secure link..."]
    })
}));
