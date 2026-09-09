import { LandingHero } from "@/components/landing/LandingHero";
import { LandingNav } from "@/components/landing/LandingNav";
import { LandingSections } from "@/components/landing/LandingSections";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-white">
      <LandingNav />
      <LandingHero />
      <LandingSections />
    </main>
  );
}
