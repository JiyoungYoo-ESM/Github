import { useEffect, useRef, useState } from "react";

/**
 * 실행 중인 분석의 경과 시간 라벨.
 *
 * CMS 조회는 콜드 상태에서 수 분까지 걸린다. 진행 표시가 없으면 멈춘 것처럼
 * 보여 사용자가 버튼을 연타하게 되고, 그게 실제 사고로 이어졌다.
 */
export function useAnalysisElapsedLabel(running: boolean): string {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startedAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (!running) {
      startedAtRef.current = null;
      setElapsedSeconds(0);
      return;
    }
    startedAtRef.current = Date.now();
    setElapsedSeconds(0);
    const timer = window.setInterval(() => {
      const startedAt = startedAtRef.current;
      if (startedAt === null) return;
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  if (!running) return "";
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  return minutes > 0 ? `${minutes}분 ${seconds}초 경과` : `${seconds}초 경과`;
}
