'use client';
import Background from '../components/Background';
import ChatInterface from '../components/ChatInterface';

export default function Home() {
  return (
    <main className="min-h-screen relative">
      <Background />
      <ChatInterface />
    </main>
  );
}
