import type { Metadata } from "next";

export const metadata: Metadata = { title: "Транспорт" };

export default function Layout({ children }: LayoutProps<"/transport">) {
  return children;
}
