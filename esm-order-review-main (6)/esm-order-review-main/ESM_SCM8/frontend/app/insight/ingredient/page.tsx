import { redirect } from "next/navigation";
import { SiliconAnalyticsWorkspace } from "@/components/redesign/SiliconAnalyticsWorkspace";
import { INGREDIENT_ANALYSIS_ENABLED } from "@/lib/feature-flags";

export default function InsightIngredientPage() {
  if (!INGREDIENT_ANALYSIS_ENABLED) redirect("/insight/input");

  return <SiliconAnalyticsWorkspace initialScreen="ingredient" />;
}
