import LoadingAnimation from '@/components/LoadingAnimation';

export default function Loading() {
    return (
        <div className="flex items-center justify-center min-h-screen bg-black">
            <LoadingAnimation />
        </div>
    );
}
