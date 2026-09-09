import Image from "next/image";
import Link from "next/link";
import { LandingAuthActions } from "@/components/landing/LandingAuthActions";

const navigationItems = [
  { label: "소개", href: "/about" },
  { label: "사용 가이드", href: "/manual" },
  { label: "발주", href: "/upload" },
  { label: "분석", href: "/insight/input" },
];

export function LandingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-black/10 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:h-[72px] sm:px-6">
        <Link href="/" className="flex items-center text-black" aria-label="Silicon2 home">
          <Image
            src="/assets/silicon2-logo-white.png"
            alt="Silicon2"
            width={200}
            height={44}
            className="h-7 w-auto object-contain [filter:invert(1)] sm:h-10"
          />
        </Link>
        <LandingAuthActions />
      </div>

      <nav className="border-t border-black/10">
        <div className="mx-auto flex h-12 max-w-7xl items-center justify-center gap-7 overflow-x-auto px-4 text-[14px] font-black text-black sm:h-[76px] sm:gap-20 sm:px-6 sm:text-xl lg:gap-24 xl:gap-28">
          {navigationItems.map((item) => (
            <Link key={item.href} href={item.href} className="whitespace-nowrap transition-colors hover:text-brand">
              {item.label}
            </Link>
          ))}
        </div>
      </nav>
    </header>
  );
}
