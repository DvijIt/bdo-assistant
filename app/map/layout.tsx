import type { Metadata } from "next";

export const metadata: Metadata = { title: "Карта" };

export default function Layout({ children }: LayoutProps<"/map">) {
  return children;
}
