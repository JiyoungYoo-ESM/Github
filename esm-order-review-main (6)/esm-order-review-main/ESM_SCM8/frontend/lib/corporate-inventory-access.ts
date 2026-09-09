import type { EntityCode } from "@/lib/entities";

const CORPORATE_INVENTORY_ALLOWED_USERNAMES = new Set(["adminmaster"]);
const CORPORATE_INVENTORY_REQUIRED_ENTITY: EntityCode = "HQ";

const CORPORATE_INVENTORY_PATH_PREFIXES = ["/overview/inventory"] as const;
const CORPORATE_INVENTORY_SCREEN_IDS = new Set(["overview"]);

type UsernameSource = string | { username: string } | null | undefined;

export function canAccessCorporateInventory(user: UsernameSource): boolean {
  const username = typeof user === "string" ? user : user?.username;
  return CORPORATE_INVENTORY_ALLOWED_USERNAMES.has((username ?? "").trim().toLowerCase());
}

export function canAccessCorporateInventoryForEntity(entityCode: EntityCode | null | undefined): boolean {
  return entityCode === CORPORATE_INVENTORY_REQUIRED_ENTITY;
}

export function isCorporateInventoryPath(pathname: string): boolean {
  return CORPORATE_INVENTORY_PATH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

export function isCorporateInventoryScreen(screen: string): boolean {
  return CORPORATE_INVENTORY_SCREEN_IDS.has(screen);
}
