import type { Metadata } from "next";

export const metadata: Metadata = { title: "Дані гри" };

export default function Layout({ children }: LayoutProps<"/game-data">) {
  return children;
}
