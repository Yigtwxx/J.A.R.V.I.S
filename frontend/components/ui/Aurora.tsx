'use client';
import { useEffect, useRef } from 'react';

export default function Aurora() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext('2d')!;
    let w = canvas.width = window.innerWidth;
    let h = canvas.height = window.innerHeight;
    let t = 0;
    let rafId: number;

    const blobs = [
      { x: 0.2, y: 0.3, r: 0.35, color: '0,243,255' },
      { x: 0.8, y: 0.2, r: 0.28, color: '0,128,255' },
      { x: 0.5, y: 0.8, r: 0.30, color: '80,0,255' },
    ];

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      blobs.forEach((b, i) => {
        const cx = (b.x + Math.sin(t * 0.0003 + i) * 0.08) * w;
        const cy = (b.y + Math.cos(t * 0.0004 + i) * 0.06) * h;
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, b.r * w);
        grad.addColorStop(0, `rgba(${b.color},0.12)`);
        grad.addColorStop(1, `rgba(${b.color},0)`);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);
      });
      t++;
      rafId = requestAnimationFrame(draw);
    };

    rafId = requestAnimationFrame(draw);

    const onResize = () => {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', onResize);
    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none z-0 opacity-70" />;
}
