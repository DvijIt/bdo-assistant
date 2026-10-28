import type { Metadata } from "next";

export const metadata: Metadata = { title: "Знання" };

export default function Layout({ children }: LayoutProps<"/knowledge">) {
  return children;
}
