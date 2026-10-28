import type { Metadata } from "next";

export const metadata: Metadata = { title: "Журнали пригод" };

export default function Layout({ children }: LayoutProps<"/journals">) {
  return children;
}
