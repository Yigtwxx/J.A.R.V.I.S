import dynamic from 'next/dynamic';

const Background = dynamic(() => import('../components/Background'));
const ChatInterface = dynamic(() => import('../components/ChatInterface'));

export default function Home() {
  return (
    <main className="min-h-screen relative">
      <Background />
      <ChatInterface />
    </main>
  );
}
