import type { Metadata } from "next";

export const metadata: Metadata = { title: "Гринд" };

export default function Layout({ children }: LayoutProps<"/grind">) {
  return children;
}
