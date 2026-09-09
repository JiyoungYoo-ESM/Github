import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number, maximumFractionDigits = 0) {
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits
  }).format(value);
}

export function formatCurrency(value: number, unit = "EUR") {
  return `${unit} ${formatNumber(value, 0)}`;
}
