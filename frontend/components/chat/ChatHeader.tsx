export default function ChatHeader() {
  return (
    <div className="sticky top-0 z-10 glass px-6 py-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-500/20 text-blue-700 font-semibold backdrop-blur-md">
          E
        </div>

        <div>
          <h1 className="text-lg font-semibold text-slate-900">Elara</h1>
          <p className="text-sm text-slate-500">
            AI patient assistant
          </p>
        </div>
      </div>
    </div>
  );
}