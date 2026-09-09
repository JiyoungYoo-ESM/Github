"use client";

import { createContext, useContext } from "react";
import type { AuthUser } from "@/lib/auth";
import type { EntityCode } from "@/lib/entities";

export type AuthSessionContextValue = {
  user: AuthUser | null;
  selectedEntity: EntityCode | null;
  selectEntity: (entityCode: EntityCode) => Promise<void>;
};

export const AuthSessionContext = createContext<AuthSessionContextValue>({
  user: null,
  selectedEntity: null,
  selectEntity: async () => undefined
});

export function useAuthSession(): AuthSessionContextValue {
  return useContext(AuthSessionContext);
}
