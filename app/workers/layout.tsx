import type { Metadata } from "next";

export const metadata: Metadata = { title: "Робітники" };

export default function Layout({ children }: LayoutProps<"/workers">) {
  return children;
}
