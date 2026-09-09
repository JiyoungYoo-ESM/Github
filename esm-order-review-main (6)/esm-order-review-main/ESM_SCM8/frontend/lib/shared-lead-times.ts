"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { getLeadTimeReference } from "@/lib/api/lead-times";
import {
  leadTimeStorageKey,
  leadTimeValuesFromMethods,
  type LeadTimeInputValues,
  type LeadTimeReference
} from "@/lib/lead-times";
import {
  onStorageAreaKeyChanged,
  readJsonItem,
  writeJsonItem
} from "@/lib/storage/adapter";

const LEAD_TIME_VALUES_CHANGED_EVENT = "esm-scm-lead-time-values-changed";

type LeadTimeSnapshot = {
  scopeKey: string | null;
  reference: LeadTimeReference | null;
  values: LeadTimeInputValues;
  loading: boolean;
  error: string;
};

const EMPTY_SNAPSHOT: LeadTimeSnapshot = {
  scopeKey: null,
  reference: null,
  values: {},
  loading: false,
  error: ""
};

function storedOverrides(scopeKey: string): LeadTimeInputValues {
  return readJsonItem<LeadTimeInputValues>("local", scopeKey, {});
}

export function useSharedLeadTimes() {
  const { user, selectedEntity } = useAuthSession();
  const scopeKey = useMemo(
    () => user && selectedEntity ? leadTimeStorageKey(user.username, selectedEntity) : null,
    [selectedEntity, user]
  );
  const [snapshot, setSnapshot] = useState<LeadTimeSnapshot>(EMPTY_SNAPSHOT);
  const visibleSnapshot = snapshot.scopeKey === scopeKey
    ? snapshot
    : {
        ...EMPTY_SNAPSHOT,
        scopeKey,
        loading: Boolean(scopeKey)
      };

  useEffect(() => {
    if (!scopeKey || !selectedEntity) {
      setSnapshot(EMPTY_SNAPSHOT);
      return;
    }

    const controller = new AbortController();
    setSnapshot({
      scopeKey,
      reference: null,
      values: {},
      loading: true,
      error: ""
    });
    void getLeadTimeReference(selectedEntity, controller.signal)
      .then((reference) => {
        if (controller.signal.aborted) return;
        setSnapshot({
          scopeKey,
          reference,
          values: leadTimeValuesFromMethods(reference.methods, storedOverrides(scopeKey)),
          loading: false,
          error: ""
        });
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setSnapshot({
          scopeKey,
          reference: null,
          values: {},
          loading: false,
          error: caught instanceof Error ? caught.message : "운송 리드타임을 불러오지 못했습니다."
        });
      });

    return () => controller.abort();
  }, [scopeKey, selectedEntity]);

  useEffect(() => {
    if (!scopeKey) return;
    const syncStoredValues = () => {
      setSnapshot((current) => {
        if (current.scopeKey !== scopeKey || !current.reference) return current;
        return {
          ...current,
          values: leadTimeValuesFromMethods(current.reference.methods, storedOverrides(scopeKey))
        };
      });
    };
    const stopStorageListener = onStorageAreaKeyChanged(scopeKey, syncStoredValues);
    window.addEventListener(LEAD_TIME_VALUES_CHANGED_EVENT, syncStoredValues);
    return () => {
      stopStorageListener();
      window.removeEventListener(LEAD_TIME_VALUES_CHANGED_EVENT, syncStoredValues);
    };
  }, [scopeKey]);

  const setLeadTime = useCallback((transportCode: string, value: string) => {
    if (
      !scopeKey ||
      !visibleSnapshot.reference?.methods.some((method) => method.code === transportCode)
    ) {
      return;
    }
    const nextStored = {
      ...storedOverrides(scopeKey),
      [transportCode]: value
    };
    writeJsonItem("local", scopeKey, nextStored);
    setSnapshot((current) => {
      if (current.scopeKey !== scopeKey) {
        return current;
      }
      return {
        ...current,
        values: {
          ...current.values,
          [transportCode]: value
        }
      };
    });
    window.dispatchEvent(new Event(LEAD_TIME_VALUES_CHANGED_EVENT));
  }, [scopeKey, visibleSnapshot.reference]);

  return {
    entityCode: visibleSnapshot.reference?.entity_code ?? selectedEntity,
    methods: visibleSnapshot.reference?.methods ?? [],
    values: visibleSnapshot.values,
    effectiveDate: visibleSnapshot.reference?.effective_date ?? "",
    source: visibleSnapshot.reference?.source ?? "",
    loading: visibleSnapshot.loading,
    error: visibleSnapshot.error,
    setLeadTime
  };
}
