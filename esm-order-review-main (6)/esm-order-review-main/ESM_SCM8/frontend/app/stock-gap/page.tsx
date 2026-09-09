import { redirect } from "next/navigation";
import { routes } from "@/lib/routes";

function toQuery(params: Record<string, string | string[] | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => query.append(key, item));
    } else if (value) {
      query.set(key, value);
    }
  });
  return query.toString();
}

export default async function StockGapPage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = toQuery(await searchParams);
  redirect(query ? `${routes.stockGap}?${query}` : routes.stockGap);
}
