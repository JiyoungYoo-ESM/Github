import Image from "next/image";
import Link from "next/link";

const footerLinks = [
  { label: "소개", href: "/about" },
  { label: "ESM", href: "/esm" },
  { label: "발주", href: "/order-analysis/order-review" },
  { label: "분석", href: "/insight/input" },
  { label: "사용설명서", href: "/manual" },
];

export function LandingFooter() {
  return (
    <footer className="border-t border-black/10 bg-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4">
          <Image
            src="/assets/silicon2-logo-white.png"
            alt="Silicon2"
            width={200}
            height={44}
            className="h-7 w-auto object-contain [filter:invert(1)]"
          />
          <span className="text-sm text-black/50">ESM SCM 발주·시장 분석 도구</span>
        </div>
        <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-medium text-black/60">
          {footerLinks.map((link) => (
            <Link key={link.href} href={link.href} className="transition-colors hover:text-brand">
              {link.label}
            </Link>
          ))}
        </nav>
        <p className="text-xs text-black/40">© {new Date().getFullYear()} Silicon2. Internal use only.</p>
      </div>
    </footer>
  );
}
