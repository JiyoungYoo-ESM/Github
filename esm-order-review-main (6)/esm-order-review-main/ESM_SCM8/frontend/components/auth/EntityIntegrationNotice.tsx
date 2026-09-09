"use client";

import { AlertTriangle } from "lucide-react";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { ENTITY_BY_CODE } from "@/lib/entities";

export function EntityIntegrationNotice() {
  const { selectedEntity } = useAuthSession();
  if (!selectedEntity) return null;
  const entity = ENTITY_BY_CODE[selectedEntity];
  if (entity.integrated) return null;
  return (
    <div className="mb-4 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900" role="status">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      {entity.displayName} 법인의 데이터 연동을 준비 중입니다. 권한은 설정되었지만 분석 데이터는 아직 제공되지 않습니다.
    </div>
  );
}
