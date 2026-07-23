'use client';

import { useCallback, useEffect, useRef } from 'react';
import { agentChatStream } from '@/services/api';
import { AgentMessage } from '@/types/profile';
import { useChatStore } from '@/store/chatStore';

/**
 * Shared autonomous-agent chat driver.
 *
 * Owns a single AbortController (independent from the OSINT search controller),
 * streams the response into the shared store, and centralises the error/abort
 * handling that ChatInputBar and AgentChatMode previously duplicated. On abort
 * it drops the orphaned user turn and clears the streaming buffer so the history
 * never ends on two consecutive user roles and no ghost bubble is left behind.
 */
export const useAgentChat = () => {
    const agentMessages = useChatStore(state => state.agentMessages);
    const setAgentMessages = useChatStore(state => state.setAgentMessages);
    const isAgentLoading = useChatStore(state => state.isAgentLoading);
    const setIsAgentLoading = useChatStore(state => state.setIsAgentLoading);
    const setStreamingAgentContent = useChatStore(state => state.setStreamingAgentContent);

    const abortControllerRef = useRef<AbortController | null>(null);

    // Abort any in-flight stream when the consuming component unmounts.
    useEffect(() => {
        return () => { abortControllerRef.current?.abort(); };
    }, []);

    const sendAgentMessage = useCallback(async (rawInput: string): Promise<void> => {
        const query = rawInput.trim();
        if (!query || isAgentLoading) return;

        // Cancel any in-flight agent stream owned by this hook.
        abortControllerRef.current?.abort();
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const userMsg: AgentMessage = { role: 'user', content: query };
        setAgentMessages(prev => [...prev, userMsg]);
        setIsAgentLoading(true);
        setStreamingAgentContent('');

        // Remove this invocation's user turn (used on abort so the history never
        // ends on two consecutive user roles) and clear the streaming buffer.
        const discardOrphanedTurn = () => {
            setAgentMessages(prev => prev.filter(m => m !== userMsg));
            setStreamingAgentContent('');
        };

        try {
            const response = await agentChatStream(query, [...agentMessages, userMsg], controller.signal);
            if (!response.ok) {
                const errBody = await response.text().catch(() => '');
                throw new Error(`Agent request failed (HTTP ${response.status})${errBody ? `: ${errBody}` : ''}`);
            }
            if (!response.body) throw new Error('No response body');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let full = '';
            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    full += decoder.decode(value, { stream: true });
                    setStreamingAgentContent(full);
                }
                full += decoder.decode(); // flush any buffered trailing multibyte char
            } catch (readError) {
                if (readError instanceof DOMException && readError.name === 'AbortError') {
                    discardOrphanedTurn();
                    return;
                }
                console.error('Agent stream read failed:', readError);
                if (!full) throw readError;
                full += '\n\n[Stream interrupted]';
            }

            setAgentMessages(prev => [...prev, { role: 'assistant', content: full }]);
            setStreamingAgentContent('');
        } catch (error: unknown) {
            if (error instanceof DOMException && error.name === 'AbortError') {
                discardOrphanedTurn();
                return;
            }
            const errMsg = error instanceof Error ? error.message : 'Unknown error';
            setAgentMessages(prev => [...prev, { role: 'assistant', content: `[ERROR] Agent failed: ${errMsg}` }]);
            setStreamingAgentContent('');
        } finally {
            setIsAgentLoading(false);
        }
    }, [agentMessages, isAgentLoading, setAgentMessages, setIsAgentLoading, setStreamingAgentContent]);

    return { sendAgentMessage, isAgentLoading };
};
