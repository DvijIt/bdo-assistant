import type { Metadata } from "next";

export const metadata: Metadata = { title: "Лайтстоуни й кристали" };

export default function Layout({ children }: LayoutProps<"/builds">) {
  return children;
}
