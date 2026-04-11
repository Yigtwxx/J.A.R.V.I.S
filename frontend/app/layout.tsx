import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import ToastProvider from "@/components/ui/ToastProvider";

export const metadata: Metadata = {
  title: { default: 'J.A.R.V.I.S - AI Assistant', template: '%s | J.A.R.V.I.S' },
  description: "Just A Rather Very Intelligent System - An AI-powered profile search assistant",
  keywords: ['OSINT', 'AI', 'JARVIS', 'profile search', 'intelligence'],
  authors: [{ name: 'J.A.R.V.I.S' }],
  robots: { index: true, follow: true },
  openGraph: {
    title: 'J.A.R.V.I.S - AI Assistant',
    description: 'Just A Rather Very Intelligent System',
    type: 'website',
    siteName: 'J.A.R.V.I.S',
  },
  twitter: {
    card: 'summary',
    title: 'J.A.R.V.I.S - AI Assistant',
    description: 'Just A Rather Very Intelligent System',
  },
  icons: { icon: '/favicon.ico' },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0a0e17',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
        <ToastProvider />
      </body>
    </html>
  );
}
