import { useChatStore } from '@/store/chatStore';

// Helper to reset store between tests
const initialState = useChatStore.getState();

beforeEach(() => {
  useChatStore.setState(initialState, true);
});

describe('chatStore', () => {
  describe('initial state', () => {
    it('has correct default values', () => {
      const state = useChatStore.getState();
      expect(state.messages).toEqual([]);
      expect(state.input).toBe('');
      expect(state.isLoading).toBe(false);
      expect(state.history).toEqual([]);
      expect(state.liveStatus).toEqual([]);
      expect(state.streamingContent).toBe('');
      expect(state.ragMessages).toEqual([]);
      expect(state.ragInput).toBe('');
      expect(state.isRagLoading).toBe(false);
      expect(state.streamingRagContent).toBe('');
      expect(state.isAgentMode).toBe(false);
      expect(state.agentMessages).toEqual([]);
      expect(state.isAgentLoading).toBe(false);
      expect(state.streamingAgentContent).toBe('');
      expect(state.activeSidePanel).toBe('history');
      expect(state.searchDepth).toBe(5);
      expect(state.activeWatches).toEqual([]);
      expect(state.userMemories).toEqual([]);
      expect(state.plugins).toEqual([]);
      expect(state.pendingActions).toEqual([]);
    });
  });

  describe('simple setters', () => {
    it('setInput updates input', () => {
      useChatStore.getState().setInput('test query');
      expect(useChatStore.getState().input).toBe('test query');
    });

    it('setIsLoading updates isLoading', () => {
      useChatStore.getState().setIsLoading(true);
      expect(useChatStore.getState().isLoading).toBe(true);
    });

    it('setSearchDepth updates searchDepth', () => {
      useChatStore.getState().setSearchDepth(8);
      expect(useChatStore.getState().searchDepth).toBe(8);
    });

    it('setAgentMode updates isAgentMode', () => {
      useChatStore.getState().setAgentMode(true);
      expect(useChatStore.getState().isAgentMode).toBe(true);
    });

    it('setActiveSidePanel updates activeSidePanel', () => {
      useChatStore.getState().setActiveSidePanel('memory');
      expect(useChatStore.getState().activeSidePanel).toBe('memory');
    });

    it('setActiveSidePanel accepts null', () => {
      useChatStore.getState().setActiveSidePanel(null);
      expect(useChatStore.getState().activeSidePanel).toBeNull();
    });

    it('setRagInput updates ragInput', () => {
      useChatStore.getState().setRagInput('rag query');
      expect(useChatStore.getState().ragInput).toBe('rag query');
    });

    it('setIsRagLoading updates isRagLoading', () => {
      useChatStore.getState().setIsRagLoading(true);
      expect(useChatStore.getState().isRagLoading).toBe(true);
    });
  });

  describe('updater-function setters', () => {
    it('setMessages with direct value', () => {
      const msgs = [{ id: '1', role: 'user' as const, content: 'hi' }];
      useChatStore.getState().setMessages(msgs);
      expect(useChatStore.getState().messages).toEqual(msgs);
    });

    it('setMessages with callback appends correctly', () => {
      const msg1 = { id: '1', role: 'user' as const, content: 'hello' };
      const msg2 = { id: '2', role: 'assistant' as const, content: 'hi' };
      useChatStore.getState().setMessages([msg1]);
      useChatStore.getState().setMessages(prev => [...prev, msg2]);
      expect(useChatStore.getState().messages).toEqual([msg1, msg2]);
    });

    it('setHistory with callback', () => {
      const item = { id: 1, query: 'test', timestamp: '2026-01-01' } as any;
      useChatStore.getState().setHistory([item]);
      useChatStore.getState().setHistory(prev => [...prev, { ...item, id: 2 }]);
      expect(useChatStore.getState().history).toHaveLength(2);
    });

    it('setStreamingContent with callback', () => {
      useChatStore.getState().setStreamingContent('start');
      useChatStore.getState().setStreamingContent(prev => prev + ' end');
      expect(useChatStore.getState().streamingContent).toBe('start end');
    });
  });

  describe('addStreamingToken', () => {
    it('appends token to streamingContent', () => {
      useChatStore.getState().addStreamingToken('hello');
      useChatStore.getState().addStreamingToken(' world');
      expect(useChatStore.getState().streamingContent).toBe('hello world');
    });

    it('converts literal \\n to actual newlines', () => {
      useChatStore.getState().addStreamingToken('line1\\nline2');
      expect(useChatStore.getState().streamingContent).toBe('line1\nline2');
    });

    it('handles multiple \\n in a single token', () => {
      useChatStore.getState().addStreamingToken('a\\nb\\nc');
      expect(useChatStore.getState().streamingContent).toBe('a\nb\nc');
    });

    it('accumulates across multiple calls with \\n conversion', () => {
      useChatStore.getState().addStreamingToken('first\\n');
      useChatStore.getState().addStreamingToken('second');
      expect(useChatStore.getState().streamingContent).toBe('first\nsecond');
    });
  });

  describe('addLiveStatus', () => {
    it('adds a status entry', () => {
      useChatStore.getState().addLiveStatus('Connecting...');
      expect(useChatStore.getState().liveStatus).toEqual(['Connecting...']);
    });

    it('keeps only last 12 entries', () => {
      for (let i = 0; i < 15; i++) {
        useChatStore.getState().addLiveStatus(`status-${i}`);
      }
      const statuses = useChatStore.getState().liveStatus;
      expect(statuses).toHaveLength(12);
      expect(statuses[0]).toBe('status-3');
      expect(statuses[11]).toBe('status-14');
    });

    it('does not truncate when under 12 entries', () => {
      for (let i = 0; i < 5; i++) {
        useChatStore.getState().addLiveStatus(`s-${i}`);
      }
      expect(useChatStore.getState().liveStatus).toHaveLength(5);
    });
  });

  describe('resetSearchState', () => {
    it('resets RAG and streaming state', () => {
      // Set some state first
      useChatStore.getState().setRagMessages([{ role: 'user', content: 'hi' } as any]);
      useChatStore.getState().setRagInput('some input');
      useChatStore.getState().setStreamingContent('partial content');
      useChatStore.getState().addLiveStatus('active status');

      // Reset
      useChatStore.getState().resetSearchState();

      const state = useChatStore.getState();
      expect(state.ragMessages).toEqual([]);
      expect(state.ragInput).toBe('');
      expect(state.streamingContent).toBe('');
      expect(state.liveStatus).toEqual(['Establishing secure link...']);
    });

    it('does not affect other state', () => {
      useChatStore.getState().setInput('keep this');
      useChatStore.getState().setIsLoading(true);
      useChatStore.getState().setAgentMode(true);

      useChatStore.getState().resetSearchState();

      const state = useChatStore.getState();
      expect(state.input).toBe('keep this');
      expect(state.isLoading).toBe(true);
      expect(state.isAgentMode).toBe(true);
    });
  });
});
