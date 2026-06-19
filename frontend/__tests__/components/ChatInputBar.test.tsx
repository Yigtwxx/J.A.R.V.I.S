import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useChatStore } from '@/store/chatStore';

// Mock framer-motion
jest.mock('framer-motion', () => ({
  motion: new Proxy({}, {
    get: (_target, prop) => {
      return React.forwardRef((props: any, ref: any) => {
        const { initial, animate, transition, whileHover, whileTap, ...rest } = props;
        return React.createElement(prop as string, { ...rest, ref });
      });
    },
  }),
  AnimatePresence: ({ children }: any) => children,
}));

// Mock child components
jest.mock('@/components/chat/VisionUpload', () => {
  return function MockVisionUpload() {
    return <div data-testid="vision-upload">VisionUpload</div>;
  };
});

jest.mock('@/components/chat/DepthSelector', () => {
  return function MockDepthSelector() {
    return <div data-testid="depth-selector">DepthSelector</div>;
  };
});

// Mock api
const mockSearchPerson = jest.fn();
const mockGetSearchHistory = jest.fn().mockResolvedValue([]);
jest.mock('@/services/api', () => ({
  searchPerson: (...args: any[]) => mockSearchPerson(...args),
  getSearchHistory: (...args: any[]) => mockGetSearchHistory(...args),
}));

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Send: (props: any) => <svg data-testid="send-icon" {...props} />,
  Loader2: (props: any) => <svg data-testid="loader-icon" {...props} />,
  Bot: (props: any) => <svg data-testid="bot-icon" {...props} />,
  Search: (props: any) => <svg data-testid="search-icon" {...props} />,
}));

// Mock next-intl — return real English copy so translation-dependent assertions hold
// (next-intl ships ESM that Jest can't parse, and there is no provider in the test tree)
jest.mock('next-intl', () => {
  const messages = require('@/messages/en.json');
  return {
    useTranslations: (namespace: string) => (key: string) => {
      const ns = (messages as Record<string, Record<string, string>>)[namespace] || {};
      return ns[key] ?? key;
    },
  };
});

import ChatInputBar from '@/components/chat/ChatInputBar';

const initialState = useChatStore.getState();

beforeEach(() => {
  useChatStore.setState(initialState, true);
  jest.clearAllMocks();
  // A successful search calls window.history.replaceState('?q=...'); reset the
  // URL so the ?q= auto-search effect does not fire across subsequent tests.
  window.history.replaceState(null, '', '/');
});

describe('ChatInputBar', () => {
  it('renders input field and send button', () => {
    render(<ChatInputBar />);

    expect(screen.getByPlaceholderText(/enter name or username/i)).toBeInTheDocument();
    expect(screen.getByTestId('send-icon')).toBeInTheDocument();
  });

  it('renders depth selector in search mode', () => {
    render(<ChatInputBar />);
    expect(screen.getByTestId('depth-selector')).toBeInTheDocument();
  });

  it('hides depth selector in agent mode', () => {
    useChatStore.getState().setAgentMode(true);
    render(<ChatInputBar />);
    expect(screen.queryByTestId('depth-selector')).not.toBeInTheDocument();
  });

  it('renders vision upload', () => {
    render(<ChatInputBar />);
    expect(screen.getByTestId('vision-upload')).toBeInTheDocument();
  });

  it('updates input on change', () => {
    render(<ChatInputBar />);

    const input = screen.getByPlaceholderText(/enter name or username/i);
    fireEvent.change(input, { target: { value: 'John Doe' } });

    expect(useChatStore.getState().input).toBe('John Doe');
  });

  it('triggers search on Enter key', async () => {
    mockSearchPerson.mockResolvedValueOnce({ name: 'John', ai_response: 'Found' });
    useChatStore.getState().setInput('John Doe');

    render(<ChatInputBar />);

    const input = screen.getByPlaceholderText(/enter name or username/i);
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(mockSearchPerson).toHaveBeenCalledWith('John Doe', 5, expect.any(AbortSignal));
    });
  });

  it('does NOT trigger search on Shift+Enter', () => {
    useChatStore.getState().setInput('test');
    render(<ChatInputBar />);

    const input = screen.getByPlaceholderText(/enter name or username/i);
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });

    expect(mockSearchPerson).not.toHaveBeenCalled();
  });

  it('does NOT search with empty input', () => {
    useChatStore.getState().setInput('   ');
    render(<ChatInputBar />);

    const button = screen.getByTestId('send-icon').closest('button')!;
    fireEvent.click(button);

    expect(mockSearchPerson).not.toHaveBeenCalled();
  });

  it('disables input when loading', () => {
    useChatStore.getState().setIsLoading(true);
    render(<ChatInputBar />);

    const input = screen.getByPlaceholderText(/enter name or username/i);
    expect(input).toBeDisabled();
  });

  it('disables send button when loading', () => {
    useChatStore.getState().setIsLoading(true);
    useChatStore.getState().setInput('test');
    render(<ChatInputBar />);

    const button = screen.getByTestId('loader-icon').closest('button')!;
    expect(button).toBeDisabled();
  });

  it('shows loader icon when loading', () => {
    useChatStore.getState().setIsLoading(true);
    render(<ChatInputBar />);

    expect(screen.getByTestId('loader-icon')).toBeInTheDocument();
  });

  it('adds assistant message on successful search', async () => {
    const response = { name: 'John', ai_response: 'Profile found' };
    mockSearchPerson.mockResolvedValueOnce(response);
    useChatStore.getState().setInput('John Doe');

    render(<ChatInputBar />);

    const input = screen.getByPlaceholderText(/enter name or username/i);
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      const msgs = useChatStore.getState().messages;
      expect(msgs).toHaveLength(2);
      expect(msgs[0].role).toBe('user');
      expect(msgs[0].content).toBe('John Doe');
      expect(msgs[1].role).toBe('assistant');
      expect(msgs[1].content).toBe('Profile found');
    });
  });

  it('adds error message on search failure', async () => {
    mockSearchPerson.mockRejectedValueOnce(new Error('Network Error'));
    useChatStore.getState().setInput('test');

    render(<ChatInputBar />);

    const input = screen.getByPlaceholderText(/enter name or username/i);
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      const msgs = useChatStore.getState().messages;
      const lastMsg = msgs[msgs.length - 1];
      expect(lastMsg.role).toBe('assistant');
      expect(lastMsg.content).toContain('[ERROR]');
      expect(lastMsg.content).toContain('Cannot reach the analysis server');
    });
  });

  it('toggles agent mode', async () => {
    const user = userEvent.setup();
    render(<ChatInputBar />);

    expect(useChatStore.getState().isAgentMode).toBe(false);

    // Find the agent toggle button (first button in the component)
    const toggleBtn = screen.getByTitle('Switch to Agent Mode');
    await user.click(toggleBtn);

    expect(useChatStore.getState().isAgentMode).toBe(true);
  });

  it('changes placeholder text in agent mode', () => {
    useChatStore.getState().setAgentMode(true);
    render(<ChatInputBar />);

    expect(screen.getByPlaceholderText(/ask the agent anything/i)).toBeInTheDocument();
  });

  it('clears input after search starts', async () => {
    mockSearchPerson.mockResolvedValueOnce({ name: 'Test', ai_response: 'ok' });
    useChatStore.getState().setInput('Test Query');

    render(<ChatInputBar />);

    const input = screen.getByPlaceholderText(/enter name or username/i);
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(useChatStore.getState().input).toBe('');
    });
  });
});
