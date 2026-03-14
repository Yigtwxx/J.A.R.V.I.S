'use client';
import { useEffect, useState } from 'react';

interface GlitchTextProps {
  text: string;
  className?: string;
  interval?: number;
}

export default function GlitchText({ text, className = '', interval = 4000 }: GlitchTextProps) {
  const [glitching, setGlitching] = useState(false);

  useEffect(() => {
    const trigger = () => {
      setGlitching(true);
      setTimeout(() => setGlitching(false), 400);
    };
    trigger();
    const id = setInterval(trigger, interval);
    return () => clearInterval(id);
  }, [interval]);

  return (
    <span
      className={`relative inline-block ${className} ${glitching ? 'animate-glitch' : ''}`}
      data-text={text}
    >
      {text}
    </span>
  );
}
