'use client';

import React from 'react';
import { motion } from 'framer-motion';

interface LoadingAnimationProps {
    subText?: string;
}

export default function LoadingAnimation({ subText }: LoadingAnimationProps) {
    return (
        <div className="flex flex-col items-center justify-center gap-6 py-4">
            {/* Refined Arc Reactor Loading */}
            <div className="relative w-20 h-20">
                <motion.div
                    className="absolute inset-0 rounded-full border border-transparent border-t-cyan-400 opacity-60"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                />
                <motion.div
                    className="absolute inset-2 rounded-full border-2 border-transparent border-t-cyan-500 border-r-cyan-500/30"
                    animate={{ rotate: -360 }}
                    transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                />
                <motion.div
                    className="absolute inset-5 rounded-full border border-transparent border-b-cyan-300 opacity-80"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                />

                {/* Center Core */}
                <motion.div
                    className="absolute inset-0 m-auto w-4 h-4 rounded-full bg-cyan-400"
                    animate={{
                        scale: [1, 1.1, 1],
                        opacity: [0.8, 1, 0.8],
                    }}
                    transition={{
                        duration: 1.5,
                        repeat: Infinity,
                        ease: "easeInOut"
                    }}
                    style={{
                        boxShadow: '0 0 15px rgba(0, 243, 255, 0.8), 0 0 30px rgba(0, 243, 255, 0.4)'
                    }}
                />
            </div>

            {/* Loading Text */}
            <div className="flex flex-col items-center gap-2">
                <motion.p
                    className="text-cyan-400 font-mono text-xs tracking-[0.2em] uppercase"
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                >
                    Processing Target Data
                </motion.p>
                <div className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                        <motion.div
                            key={i}
                            className="w-1 h-1 bg-cyan-500 rounded-full"
                            animate={{ opacity: [0.2, 1, 0.2] }}
                            transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                        />
                    ))}
                </div>
                {subText && (
                    <motion.p
                        key={subText}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 0.6 }}
                        transition={{ duration: 0.4 }}
                        className="text-cyan-600 font-mono text-[10px] tracking-wider max-w-xs text-center truncate"
                    >
                        {subText}
                    </motion.p>
                )}
            </div>
        </div>
    );
}
