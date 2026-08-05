export function Forbidden() {
  return (
    <div className="rounded-lg border border-red-900/60 bg-red-950/30 p-10 text-center">
      <p className="text-sm text-red-300">이 페이지를 볼 권한이 없습니다.</p>
      <p className="mt-2 text-xs text-red-400/70">
        권한은 서버에서 다시 확인됩니다 — 화면을 감춘 것이 접근을 막는 것은 아닙니다.
      </p>
    </div>
  );
}
