'use client';
import { useEffect, useRef, useState } from 'react';

const CHARS = '!<>-_\\/[]{}—=+*^?#@$%&';

interface ScrambleTextProps {
  text: string;
  className?: string;
  trigger?: 'mount' | 'hover';
  speed?: number;
}

export default function ScrambleText({ text, className, trigger = 'mount', speed = 40 }: ScrambleTextProps) {
  const [display, setDisplay] = useState(trigger === 'mount' ? '' : text);
  const frameRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scramble = () => {
    let iteration = 0;
    if (frameRef.current) clearInterval(frameRef.current);
    frameRef.current = setInterval(() => {
      setDisplay(
        text.split('').map((char, i) => {
          if (char === ' ') return ' ';
          if (i < iteration) return text[i];
          return CHARS[Math.floor(Math.random() * CHARS.length)];
        }).join('')
      );
      if (iteration >= text.length) clearInterval(frameRef.current!);
      iteration += 1 / 2;
    }, speed);
  };

  useEffect(() => {
    if (trigger === 'mount') scramble();
    return () => { if (frameRef.current) clearInterval(frameRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  if (trigger === 'hover') {
    return <span className={className} onMouseEnter={scramble}>{display}</span>;
  }
  return <span className={className}>{display}</span>;
}
