"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOutIcon, BotIcon, BookOpenIcon, DatabaseIcon, PanelsTopLeftIcon, MoreHorizontalIcon, PanelLeftCloseIcon, PanelLeftOpenIcon, PlusIcon, SquarePenIcon, Trash2Icon, XIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { toast } from "sonner";
import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Sidebar, SidebarFooter, SidebarContent, SidebarGroup, SidebarGroupAction, SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuAction, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAccess } from "@/lib/access/provider";
import { useConversationSelection, useWorkspace } from "@/lib/services/provider";

function SidebarBrand() {
  const { state, isMobile, toggleSidebar } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;
  const closeButton = <Button type="button" variant="ghost" size="icon" aria-label={isMobile ? "关闭导航" : "收起侧边栏"} aria-expanded={true} onClick={toggleSidebar}>
    {isMobile ? <XIcon /> : <PanelLeftCloseIcon />}
  </Button>;

  return <SidebarHeader className="shrink-0 px-2 pb-1 pt-3">
    <div className="flex h-10 items-center gap-2 group-data-[collapsible=icon]:justify-center">
      {collapsed ? <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <Button type="button" variant="ghost" size="icon-lg" className="group/brand relative size-10" aria-label="展开侧边栏" aria-expanded={false} onClick={toggleSidebar}>
            <span data-slot="sidebar-brand-mark" className="grid place-items-center transition-opacity group-hover/brand:opacity-0 group-focus-visible/brand:opacity-0 motion-reduce:transition-none"><BrandMark /></span>
            <span data-slot="sidebar-expand-icon" className="absolute inset-0 grid place-items-center opacity-0 transition-opacity group-hover/brand:opacity-100 group-focus-visible/brand:opacity-100 motion-reduce:transition-none"><PanelLeftOpenIcon /></span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={10}>展开侧边栏</TooltipContent>
      </Tooltip> : <>
        <Link href="/chat" aria-label="小马助手首页" className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring">
          <BrandMark />
          <span className="truncate text-base font-semibold tracking-tight">小马助手</span>
        </Link>
        {isMobile ? closeButton : <Tooltip delayDuration={300}>
          <TooltipTrigger asChild>{closeButton}</TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>收起侧边栏</TooltipContent>
        </Tooltip>}
      </>}
    </div>
  </SidebarHeader>;
}

function Navigation() {
  const { user, logout } = useAccess();
  const pathname = usePathname();
  const router = useRouter();
  const { setOpenMobile } = useSidebar();
  const { conversations, repository } = useWorkspace();
  const { activeId, setActiveId } = useConversationSelection();
  const navigate = (href: string) => { router.push(href); setOpenMobile(false); };
  const startNewConversation = () => { setActiveId(null); navigate("/chat"); };
  return <Sidebar collapsible="icon" variant="inset">
    <SidebarBrand />
      <SidebarGroup className="shrink-0 pb-0">
        <SidebarMenu className="group-data-[collapsible=icon]:items-center">
          {[
            { title: "新建对话", href: "/chat", icon: SquarePenIcon, active: pathname === "/chat" && !activeId },
            { title: "知识库", href: "/knowledge", icon: BookOpenIcon, active: pathname.startsWith("/knowledge") },
            { title: "数据源", href: "/data-sources", icon: DatabaseIcon, active: pathname.startsWith("/data-sources") },
            ...(user?.role === "admin" ? [{ title: "Agent 配置", href: "/agents", icon: BotIcon, active: pathname.startsWith("/agents") }] : []),
            { title: "项目介绍", href: "/project", icon: PanelsTopLeftIcon, active: pathname.startsWith("/project") },
          ].map(item => <SidebarMenuItem key={item.href}>
            <SidebarMenuButton className="h-10" tooltip={item.title} isActive={item.active} aria-current={item.active ? "page" : undefined} onClick={() => { if (item.href === "/chat") startNewConversation(); else navigate(item.href); }}><item.icon strokeWidth={1.7} /><span>{item.title}</span></SidebarMenuButton>
          </SidebarMenuItem>)}
        </SidebarMenu>
      </SidebarGroup>
    <SidebarGroup className="group/recent shrink-0 pb-0 group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>最近对话</SidebarGroupLabel>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild><SidebarGroupAction aria-label="新建对话" onClick={startNewConversation} className="opacity-0 transition-opacity group-hover/recent:opacity-100 group-focus-within/recent:opacity-100 focus-visible:ring-2 [@media(hover:none)]:opacity-100 motion-reduce:transition-none"><PlusIcon /><span className="sr-only">新建对话</span></SidebarGroupAction></TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>新建对话</TooltipContent>
      </Tooltip>
    </SidebarGroup>
    <SidebarContent role="region" aria-label="最近对话列表" className="overscroll-contain">
      <SidebarGroup className="pt-0 group-data-[collapsible=icon]:hidden">
        <SidebarMenu>
          {conversations.map(conversation => <SidebarMenuItem key={conversation.id}>
            <SidebarMenuButton className="h-9" isActive={pathname === "/chat" && activeId === conversation.id} onClick={() => { setActiveId(conversation.id); navigate("/chat"); }}><span className="min-w-0 flex-1 truncate" title={conversation.title}>{conversation.title}</span>{["queued", "running"].includes(conversation.messages.at(-1)?.status ?? "") && <Spinner aria-label={conversation.messages.at(-1)?.status === "queued" ? "排队中" : "运行中"} className="ml-auto shrink-0" />}</SidebarMenuButton>
            <DropdownMenu>
              <DropdownMenuTrigger asChild><SidebarMenuAction showOnHover aria-label={`对话操作：${conversation.title}`}><MoreHorizontalIcon /><span className="sr-only">对话操作</span></SidebarMenuAction></DropdownMenuTrigger>
              <DropdownMenuContent side="bottom" align="end" className="w-36">
                <DropdownMenuGroup><DropdownMenuItem variant="destructive" onSelect={() => {
                  const removed = repository.removeConversation(conversation.id);
                  if (!removed) return;
                  const wasActive = activeId === conversation.id;
                  if (wasActive) setActiveId(null);
                  toast("已删除对话", { duration: 8000, action: { label: "撤销", onClick: () => {
                    repository.restoreConversation(removed.conversation, removed.index);
                    if (wasActive) setActiveId(removed.conversation.id);
                  } } });
                }}><Trash2Icon />删除对话</DropdownMenuItem></DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>)}
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter className="shrink-0"><SidebarMenu><SidebarMenuItem><SidebarMenuButton tooltip="退出登录" onClick={() => { void logout(); }}><LogOutIcon /><span>退出</span></SidebarMenuButton></SidebarMenuItem></SidebarMenu></SidebarFooter>
  </Sidebar>;
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return <AdminShell>{children}</AdminShell>;
  return <SidebarProvider style={{ "--sidebar-width": "232px", "--sidebar-width-icon": "56px" } as CSSProperties} className="h-svh min-h-0 overflow-hidden">
    <Navigation />
    <SidebarInset className="min-w-0 overflow-hidden">
      <div className="absolute left-3 top-3 md:hidden"><SidebarTrigger aria-label="打开导航" /></div>
      {children}
    </SidebarInset>
  </SidebarProvider>;
}

function AdminShell({ children }: { children: ReactNode }) {
  const { logout } = useAccess();
  return <div className="flex h-svh min-h-0 flex-col gap-2 overflow-hidden bg-sidebar p-2">
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 px-2 md:px-4">
      <Link href="/chat" aria-label="返回小马助手" className="flex min-w-0 items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring"><BrandMark /><span className="truncate font-semibold">小马助手</span></Link>
      <div className="flex items-center gap-2"><Button variant="outline" size="sm" asChild><Link href="/chat">返回助手</Link></Button><Button variant="ghost" size="sm" onClick={() => { void logout(); }}><LogOutIcon data-icon="inline-start" />退出登录</Button></div>
    </header>
    <main className="flex min-h-0 flex-1 overflow-hidden rounded-xl border bg-background">{children}</main>
  </div>;
}
