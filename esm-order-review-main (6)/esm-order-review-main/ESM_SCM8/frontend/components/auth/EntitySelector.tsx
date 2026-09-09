"use client";

import { Building2 } from "lucide-react";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { allowedEntityOptions, type EntityCode } from "@/lib/entities";

export function EntitySelector() {
  const { user, selectedEntity, selectEntity } = useAuthSession();
  const options = allowedEntityOptions(user?.allowed_entities ?? []);
  if (!user || !selectedEntity || options.length === 0) return null;

  return (
    <label className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-white px-3 text-xs font-bold text-slate-600">
      <Building2 className="h-4 w-4 text-brand" />
      <span className="sr-only">법인 선택</span>
      <select
        aria-label="법인 선택"
        value={selectedEntity}
        onChange={(event) => void selectEntity(event.target.value as EntityCode)}
        className="max-w-[190px] bg-transparent text-xs font-bold text-ink outline-none"
      >
        {options.map((entity) => (
          <option key={entity.code} value={entity.code}>
            {entity.displayName}{entity.integrated ? "" : " · 준비 중"}
          </option>
        ))}
      </select>
    </label>
  );
}
