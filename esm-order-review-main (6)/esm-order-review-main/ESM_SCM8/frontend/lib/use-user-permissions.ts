"use client";

import { useMemo } from "react";

import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { getUserPermissions } from "@/lib/amount-permissions";

export function useUserPermissions() {
  const { user } = useAuthSession();
  return useMemo(
    () => user?.permissions ?? getUserPermissions(user?.username),
    [user?.permissions, user?.username]
  );
}
