import { allowedEntityOptions, isEntityCode, type EntityCode } from "./entities.ts";

export type EntitySessionUser = {
  username: string;
  allowed_entities: EntityCode[];
};

const SELECTED_ENTITY_PREFIX = "esm_scm_selected_entity:";
let activeEntityCode: EntityCode | null = null;

function storageKey(username: string) {
  return `${SELECTED_ENTITY_PREFIX}${username}`;
}

export function getActiveEntityCode(): EntityCode | null {
  return activeEntityCode;
}

export function setActiveEntityCode(user: EntitySessionUser, entityCode: EntityCode): void {
  if (!user.allowed_entities.includes(entityCode)) {
    throw new Error("허용되지 않은 법인입니다.");
  }
  activeEntityCode = entityCode;
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(storageKey(user.username), entityCode);
  }
}

export function initializeActiveEntity(user: EntitySessionUser): EntityCode {
  const options = allowedEntityOptions(user.allowed_entities);
  if (options.length === 0) {
    throw new Error("사용 가능한 법인이 없습니다.");
  }
  let candidate: string | null = null;
  if (typeof window !== "undefined") {
    const queryEntity = new URLSearchParams(window.location.search).get("entity");
    if (queryEntity) {
      if (isEntityCode(queryEntity) && user.allowed_entities.includes(queryEntity)) {
        candidate = queryEntity;
      } else {
        const url = new URL(window.location.href);
        url.searchParams.delete("entity");
        window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
      }
    }
    candidate ??= window.sessionStorage.getItem(storageKey(user.username));
  }
  const selected =
    (isEntityCode(candidate) && user.allowed_entities.includes(candidate) ? candidate : null) ??
    options.find((entity) => entity.code === "PL")?.code ??
    options.find((entity) => entity.integrated)?.code ??
    options[0].code;
  setActiveEntityCode(user, selected);
  return selected;
}

export function clearActiveEntity(): void {
  activeEntityCode = null;
  if (typeof window === "undefined") return;
  for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = window.sessionStorage.key(index);
    if (key?.startsWith(SELECTED_ENTITY_PREFIX)) {
      window.sessionStorage.removeItem(key);
    }
  }
}
