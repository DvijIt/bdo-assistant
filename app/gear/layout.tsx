import type { Metadata } from "next";

export const metadata: Metadata = { title: "Спорядження" };

export default function Layout({ children }: LayoutProps<"/gear">) {
  return children;
}
