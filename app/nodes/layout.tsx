import type { Metadata } from "next";

export const metadata: Metadata = { title: "Вузли" };

export default function Layout({ children }: LayoutProps<"/nodes">) {
  return children;
}
