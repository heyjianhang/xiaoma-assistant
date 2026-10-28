"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpenIcon, ChevronRightIcon, CircleHelpIcon, ClipboardCheckIcon, ClockIcon, DatabaseIcon, ScaleIcon, ShieldCheckIcon, TriangleAlertIcon, TrendingUpIcon } from "lucide-react";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { promptCases, promptGroups } from "./prompt-cases";

const featured = [
  { id: "Q01", label: "制度版本", icon: BookOpenIcon },
  { id: "Q14", label: "经营指标", icon: DatabaseIcon },
  { id: "Q03", label: "月报核对", icon: ScaleIcon },
  { id: "Q07", label: "退款超时", icon: ClockIcon },
  { id: "Q06", label: "口径澄清", icon: CircleHelpIcon },
  { id: "Q05", label: "小样本分析", icon: TriangleAlertIcon },
  { id: "Q13", label: "订单趋势", icon: TrendingUpIcon },
  { id: "Q02", label: "供应商准入", icon: ShieldCheckIcon },
  { id: "Q25", label: "报表复核", icon: ClipboardCheckIcon },
];

interface ChatPromptSuggestionsProps {
  busy: boolean;
  onSelect: (question: string) => void;
  onFocusInput: () => void;
}

export function ChatPromptSuggestions({ busy, onSelect, onFocusInput }: ChatPromptSuggestionsProps) {
  const [open, setOpen] = useState(false);
  const stripRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: true });
  useEffect(() => {
    const viewport = stripRef.current?.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]');
    if (!viewport) return;
    const updateEdges = () => setEdges({ left: viewport.scrollLeft > 1, right: viewport.scrollLeft + viewport.clientWidth < viewport.scrollWidth - 1 });
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey) return;
      const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
      const scale = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientWidth : 1;
      const previous = viewport.scrollLeft;
      viewport.scrollLeft += delta * scale;
      if (viewport.scrollLeft !== previous) event.preventDefault();
    };
    const observer = new ResizeObserver(updateEdges);
    observer.observe(viewport);
    if (viewport.firstElementChild) observer.observe(viewport.firstElementChild);
    viewport.addEventListener("scroll", updateEdges, { passive: true });
    viewport.addEventListener("wheel", onWheel, { passive: false });
    updateEdges();
    return () => { observer.disconnect(); viewport.removeEventListener("scroll", updateEdges); viewport.removeEventListener("wheel", onWheel); };
  }, []);
  const mask = `linear-gradient(to right, ${edges.left ? "transparent, black 20px" : "black"}, ${edges.right ? "black calc(100% - 36px), transparent" : "black"})`;
  return <nav aria-label="测试用例" className="flex min-w-0 items-center gap-2">
    <div ref={stripRef} className="min-w-0 flex-1 overflow-hidden" style={{ maskImage: mask, WebkitMaskImage: mask }}>
    <Suggestions aria-label="横向滑动选择用例" className="gap-2 px-0.5 py-1">
      {featured.map(item => {
        const prompt = promptCases.find(prompt => prompt.id === item.id)!;
        return <Suggestion key={item.id} suggestion={prompt.question} aria-label={`填入用例：${item.label}`} disabled={busy} onClick={onSelect}><item.icon data-icon="inline-start" />{item.label}</Suggestion>;
      })}
    </Suggestions>
    </div>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button type="button" variant="ghost" size="sm" disabled={busy}>更多用例<ChevronRightIcon data-icon="inline-end" /></Button></DialogTrigger>
      <DialogContent className="gap-3 overflow-hidden sm:max-w-2xl" onCloseAutoFocus={event => { event.preventDefault(); onFocusInput(); }}>
        <DialogHeader>
          <DialogTitle>测试用例</DialogTitle>
          <DialogDescription className="sr-only">搜索或按场景选择问题，填入输入框后可修改并发送。场景分类不指定实际查询路由。</DialogDescription>
        </DialogHeader>
        <Command>
          <CommandInput aria-label="搜索测试用例" placeholder="搜索问题、场景或编号…" />
          <CommandList className="max-h-[min(60svh,480px)]">
            <CommandEmpty>没有找到匹配的用例</CommandEmpty>
            {promptGroups.map(group => <CommandGroup key={group} heading={group}>
              {promptCases.filter(prompt => prompt.group === group).map(prompt => <CommandItem key={prompt.id} value={prompt.question} keywords={[prompt.id, group]} className="items-start gap-3 py-3" onSelect={() => { onSelect(prompt.question); setOpen(false); }}>
                <span className="pt-0.5 font-mono text-xs text-muted-foreground">{prompt.id}</span>
                <span className="whitespace-normal leading-6">{prompt.question}</span>
              </CommandItem>)}
            </CommandGroup>)}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  </nav>;
}
