import type { Metadata } from "next";
import { DM_Sans, Manrope } from "next/font/google";
import "./globals.css";

// Шрифти вбудовуються під час збірки: застосунок працює локально й не ходить у Google Fonts.
const dmSans = DM_Sans({ variable: "--font-body", subsets: ["latin", "latin-ext"] });
const manrope = Manrope({ variable: "--font-heading", subsets: ["latin", "cyrillic"] });

export const metadata: Metadata = {
  // Назви вкладок розділів задають їхні layout.tsx.
  title: { default: "Огляд · BDO Companion", template: "%s · BDO Companion" },
  description: "Особистий помічник для Black Desert Online: персонажі, ресурси, робітники й знання з трафіку гри.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="uk" className={`${dmSans.variable} ${manrope.variable}`}>
      <body>{children}</body>
    </html>
  );
}
