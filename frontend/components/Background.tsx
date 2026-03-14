'use client';

import React from 'react';
import { motion } from 'framer-motion';
import Aurora from '@/components/ui/Aurora';

export default function Background() {
    return (
        <>
            {/* Aurora ambient glow layer */}
            <Aurora />

            {/* Scan Line */}
            <div className="scan-line" />

            {/* Grid Background */}
            <div className="fixed inset-0 grid-background opacity-20 pointer-events-none" />

            {/* Floating Arc Reactors */}
            <motion.div
                className="fixed top-20 right-20 arc-reactor pointer-events-none"
                animate={{
                    scale: [1, 1.2, 1],
                    opacity: [0.3, 0.6, 0.3],
                }}
                transition={{
                    duration: 4,
                    repeat: Infinity,
                    ease: "easeInOut"
                }}
            />

            <motion.div
                className="fixed bottom-20 left-20 arc-reactor pointer-events-none"
                animate={{
                    scale: [1.2, 1, 1.2],
                    opacity: [0.6, 0.3, 0.6],
                }}
                transition={{
                    duration: 4,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: 2
                }}
            />

            {/* Vignette Effect */}
            <div className="fixed inset-0 pointer-events-none"
                style={{
                    background: 'radial-gradient(circle at center, transparent 0%, rgba(5, 8, 22, 0.8) 100%)'
                }}
            />
        </>
    );
}
