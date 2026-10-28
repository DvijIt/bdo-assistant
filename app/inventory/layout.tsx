import type { Metadata } from "next";

export const metadata: Metadata = { title: "Ресурси" };

export default function Layout({ children }: LayoutProps<"/inventory">) {
  return children;
}
