import type { Metadata } from "next";

export const metadata: Metadata = { title: "Квести" };

export default function Layout({ children }: LayoutProps<"/quests">) {
  return children;
}
