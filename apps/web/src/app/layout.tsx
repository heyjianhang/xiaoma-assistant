import { AccessProvider } from "@/lib/access/provider";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@fontsource-variable/geist";
import "./globals.css";
import { WorkspaceShell } from "@/components/workspace-shell";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { WorkspaceProvider } from "@/lib/services/provider";

export const metadata: Metadata = {
  title: "小马助手",
  description: "小马助手：业务文档与数据问答系统。",
  icons: { icon: { url: "/images/cyber-pony-pixel.webp", type: "image/webp" } },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="zh-CN"><body><TooltipProvider><AccessProvider><WorkspaceProvider><WorkspaceShell>{children}</WorkspaceShell></WorkspaceProvider></AccessProvider><Toaster /></TooltipProvider></body></html>;
}
