// 옛 주소(/order-review) 호환용 리다이렉트 껍데기입니다. 화면을 그리지 않습니다.
// 실제 발주분석 화면은 /order-analysis/order-review (components/redesign/SiliconAnalyticsWorkspace)에 있습니다.
// 옛 북마크·공유 링크가 404가 되지 않도록 유지 중이니 삭제하지 마세요.
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

export default async function OrderReviewPage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = toQuery(await searchParams);
  redirect(query ? `${routes.orderAnalysis}?${query}` : routes.orderAnalysis);
}
