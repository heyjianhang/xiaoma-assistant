"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeftIcon, ArrowUpRightIcon, BarChart3Icon, BookOpenIcon, ChevronRightIcon, CircleHelpIcon, DatabaseIcon, GaugeIcon, ScaleIcon, Table2Icon, TrendingUpIcon } from "lucide-react";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { promptCases, promptGroups } from "./prompt-cases";
import { PromptCaseDetails } from "./prompt-case-details";

const groupIcons = { "文档问答": BookOpenIcon, "数据查询": DatabaseIcon, "综合核对": ScaleIcon, "异常澄清": CircleHelpIcon, "ChatBI": BarChart3Icon };
const viewIcons = { "指标卡": GaugeIcon, "柱状图": BarChart3Icon, "折线图": TrendingUpIcon, "数据表": Table2Icon };

interface ChatPromptSuggestionsProps {
  busy: boolean;
  onSelect: (question: string) => void;
  onFocusInput: () => void;
}

export function ChatPromptSuggestions({ busy, onSelect, onFocusInput }: ChatPromptSuggestionsProps) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = promptCases.find(prompt => prompt.id === selectedId);
  const searchRef = useRef<HTMLInputElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) (selected ? backRef.current : searchRef.current)?.focus({ preventScroll: true });
  }, [open, selected]);
  function showCase(id: string) { setSelectedId(id); setOpen(true); }
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
      {promptCases.map(prompt => {
        const Icon = viewIcons[prompt.components[0] as keyof typeof viewIcons] ?? groupIcons[prompt.group as keyof typeof groupIcons] ?? BookOpenIcon;
        return <Suggestion key={prompt.id} suggestion={prompt.question} aria-label={`查看用例：${prompt.label}`} disabled={busy} onClick={() => showCase(prompt.id)}><Icon data-icon="inline-start" />{prompt.label}</Suggestion>;
      })}
    </Suggestions>
    </div>
    <Dialog open={open} onOpenChange={next => { if (next) setSelectedId(null); setOpen(next); }}>
      <DialogTrigger asChild><Button type="button" variant="ghost" size="sm" disabled={busy}>更多用例<ChevronRightIcon data-icon="inline-end" /></Button></DialogTrigger>
      <DialogContent className="flex h-[min(82svh,720px)] flex-col gap-4 overflow-hidden p-5 sm:max-w-3xl sm:p-6" onCloseAutoFocus={event => { event.preventDefault(); onFocusInput(); }}>
        <DialogHeader className="shrink-0 pr-8">
          <div className="flex items-center gap-2">
            {selected && <Button ref={backRef} type="button" variant="ghost" size="icon-sm" aria-label="返回用例列表" onClick={() => setSelectedId(null)}><ArrowLeftIcon /></Button>}
            <DialogTitle>{selected ? selected.label : "测试用例"}</DialogTitle>
            {selected && <Badge variant="outline">{selected.id}</Badge>}
            {!selected && <Badge variant="secondary">{promptCases.length}</Badge>}
          </div>
          <DialogDescription className="sr-only">选择问题查看预期答案、所需资料与验收要点；填入时只使用问题本身，不自动发送。</DialogDescription>
        </DialogHeader>
        <Command className={selected ? "hidden" : "min-h-0 flex-1"} filter={(value, search, keywords = []) => {
          const query = search.trim().toLowerCase();
          if (/^a\d+$/.test(query)) return value.toLowerCase() === query ? 1 : 0;
          const text = [value, ...keywords].join(" ").toLowerCase();
          return query.split(/\s+/).every(term => text.includes(term)) ? 1 : 0;
        }}>
          <CommandInput ref={searchRef} aria-label="搜索测试用例" placeholder="搜索问题、场景或编号…" />
          <CommandList className="min-h-0 max-h-none flex-1">
            <CommandEmpty>没有找到匹配的用例</CommandEmpty>
            {promptGroups.map(group => <CommandGroup key={group} heading={`${group} · ${promptCases.filter(prompt => prompt.group === group).length}`}>
              {promptCases.filter(prompt => prompt.group === group).map(prompt => <CommandItem key={prompt.id} value={prompt.id} keywords={[prompt.question, prompt.label, group, prompt.expected_route, ...prompt.components]} aria-label={`查看用例 ${prompt.id}：${prompt.label}`} className="items-start gap-3 py-3" onSelect={() => setSelectedId(prompt.id)}>
                <span className="pt-0.5 font-mono text-xs text-muted-foreground">{prompt.id}</span>
                <span className="flex min-w-0 flex-1 flex-col gap-1"><span className="font-medium">{prompt.label}</span><span className="whitespace-normal leading-6 text-muted-foreground">{prompt.question}</span></span>
                <ChevronRightIcon className="mt-0.5 text-muted-foreground" />
              </CommandItem>)}
            </CommandGroup>)}
          </CommandList>
        </Command>
        {selected && <>
          <div key={selected.id} className="min-h-0 flex-1 overflow-y-auto pr-1"><PromptCaseDetails prompt={selected} /></div>
          <div className="flex shrink-0 justify-end pt-1"><Button type="button" disabled={busy} onClick={() => { onSelect(selected.question); setOpen(false); }}>填入问题<ArrowUpRightIcon data-icon="inline-end" /></Button></div>
        </>}
      </DialogContent>
    </Dialog>
  </nav>;
}
