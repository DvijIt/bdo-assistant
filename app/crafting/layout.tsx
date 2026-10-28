import type { Metadata } from "next";

export const metadata: Metadata = { title: "Що зготувати" };

export default function Layout({ children }: LayoutProps<"/crafting">) {
  return children;
}
