import type { EntityCode } from "@/lib/entities";
import { readRawItem, removeItem, writeRawItem } from "@/lib/storage/adapter";

const STORAGE_PREFIX = "esm_scm_order_v3_running_job";
const LEGACY_STORAGE_PREFIX = "esm_scm_order_v3_active_job";
const JOB_ID_PATTERN = /^order3_[A-Za-z0-9_-]+$/;

function storageKey(prefix: string, username: string, entityCode: EntityCode): string {
  return `${prefix}:${encodeURIComponent(username)}:${entityCode}`;
}

export function loadOrderV3ActiveJob(username: string, entityCode: EntityCode): string | null {
  // The legacy key also retained completed jobs, which made yesterday's result
  // look like the user's only available action. Remove it during migration.
  removeItem("local", storageKey(LEGACY_STORAGE_PREFIX, username, entityCode));
  const key = storageKey(STORAGE_PREFIX, username, entityCode);
  const jobId = readRawItem("local", key);
  if (!jobId || !JOB_ID_PATTERN.test(jobId)) {
    removeItem("local", key);
    return null;
  }
  return jobId;
}

export function saveOrderV3ActiveJob(
  username: string,
  entityCode: EntityCode,
  jobId: string,
): void {
  if (JOB_ID_PATTERN.test(jobId)) {
    writeRawItem("local", storageKey(STORAGE_PREFIX, username, entityCode), jobId);
  }
}

export function clearOrderV3ActiveJob(username: string, entityCode: EntityCode): void {
  removeItem("local", storageKey(STORAGE_PREFIX, username, entityCode));
  removeItem("local", storageKey(LEGACY_STORAGE_PREFIX, username, entityCode));
}
