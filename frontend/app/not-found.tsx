import Link from 'next/link';

export default function NotFound() {
    return (
        <div className="flex items-center justify-center min-h-screen bg-black text-cyan-400 font-mono">
            <div className="text-center space-y-6 relative">
                {/* Scan line effect */}
                <div className="absolute inset-0 pointer-events-none overflow-hidden">
                    <div className="absolute inset-0 bg-[linear-gradient(transparent_50%,rgba(0,255,255,0.03)_50%)] bg-[length:100%_4px]" />
                </div>

                <p className="text-8xl font-orbitron font-black tracking-widest drop-shadow-[0_0_30px_rgba(0,255,255,0.5)]">
                    404
                </p>
                <p className="text-xl font-bold tracking-[0.3em] uppercase">
                    [TARGET NOT FOUND]
                </p>
                <p className="text-sm text-cyan-400/60 max-w-md mx-auto">
                    The requested resource does not exist in J.A.R.V.I.S. database.
                </p>
                <Link
                    href="/"
                    className="inline-block px-6 py-3 border border-cyan-500/50 rounded-lg hover:bg-cyan-950/40 transition-colors text-sm tracking-widest uppercase"
                >
                    Return to Base
                </Link>
            </div>
        </div>
    );
}
