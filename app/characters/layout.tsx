import type { Metadata } from "next";

export const metadata: Metadata = { title: "Персонажі" };

export default function Layout({ children }: LayoutProps<"/characters">) {
  return children;
}
