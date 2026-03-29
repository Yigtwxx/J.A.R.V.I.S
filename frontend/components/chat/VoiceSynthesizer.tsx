'use client';

import { useCallback, useEffect } from 'react';
import { useChatStore } from '@/store/chatStore';

const VoiceSynthesizer = () => {
    const messages = useChatStore(state => state.messages);
    const voiceEnabled = useChatStore(state => state.voiceEnabled);
    const isSpeaking = useChatStore(state => state.isSpeaking);
    const setIsSpeaking = useChatStore(state => state.setIsSpeaking);

    const speakResponse = useCallback((text: string) => {
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

export default VoiceSynthesizer;
