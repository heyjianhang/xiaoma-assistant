"use client";

import { useRef, useState, type Dispatch, type RefObject, type SetStateAction } from "react";
import { BookOpenIcon, DatabaseIcon, PlusIcon, WrenchIcon, SparklesIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { PromptInput, PromptInputBody, PromptInputHeader, PromptInputButton, PromptInputFooter, PromptInputSubmit, PromptInputTextarea, PromptInputTools } from "@/components/ai-elements/prompt-input";
import { SpeechInput } from "@/components/ai-elements/speech-input";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandList, CommandGroup, CommandItem, CommandEmpty } from "@/components/ui/command";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { skillAvailable, type ChatSkill } from "./chat-skills";
import { Switch } from "@/components/ui/switch";
import { knowledgeFilesError, UploadDialog } from "@/features/knowledge/upload-dialog";
import type { ChatToolAccess } from "@/lib/services/contracts";
import { ChatModelSelector } from "./chat-model-selector";

import { useAccess } from "@/lib/access/provider";

interface ChatComposerProps {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  onDraftChange: Dispatch<SetStateAction<string>>;
  modelId: string;
  onModelChange: (value: string) => void;
  toolAccess: ChatToolAccess;
  onToolAccessChange: (value: ChatToolAccess) => void;
  busy: boolean;
  onSend: (question: string) => void;
  onStop: () => void;
  disabled?: boolean;
  skills: ChatSkill[];
  skillError: string;
  selectedSkills: string[];
  onSkillsChange: Dispatch<SetStateAction<string[]>>;
}

export function ChatComposer({ inputRef, draft, onDraftChange, modelId, onModelChange, toolAccess, onToolAccessChange, busy, onSend, onStop, disabled = false, skills, skillError, selectedSkills, onSkillsChange }: ChatComposerProps) {
  const { user } = useAccess();
  const [uploadFiles, setUploadFiles] = useState<File[] | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const [dismissed, setDismissed] = useState(false);
  const [activeSkill, setActiveSkill] = useState("");
  const query = /^\/([^\s]*)$/.exec(draft)?.[1];
  const menuOpen = query !== undefined && !dismissed && !busy && !disabled;
  const matches = skills.filter(skill => !selectedSkills.includes(skill.id) && `${skill.id} ${skill.name} ${skill.description}`.toLowerCase().includes((query ?? "").toLowerCase()));
  const selectable = matches.filter(skill => skillAvailable(skill, toolAccess));
  function chooseSkill(id: string) {
    const skill = skills.find(item => item.id === id);
    if (!skill || !skillAvailable(skill, toolAccess) || selectedSkills.length >= 5) return;
    onSkillsChange(previous => [...previous, id]); onDraftChange(""); setDismissed(true); setActiveSkill(""); inputRef.current?.focus();
  }
  return <>
    <input ref={uploadRef} type="file" className="hidden" aria-label="选择知识文档" accept=".pdf,.md,.markdown" multiple onChange={event => {
      const incoming = Array.from(event.target.files ?? []);
      event.target.value = "";
      if (!incoming.length) return;
      const error = knowledgeFilesError(incoming);
      if (error) toast.error(error); else setUploadFiles(incoming);
    }} />
    <Popover open={menuOpen} onOpenChange={open => { if (!open) setDismissed(true); }}>
    <PopoverAnchor asChild><div>
    <PromptInput aria-label="消息输入框" maxFiles={0}
      onError={() => toast.info("当前对话支持文本提问，文档请到知识库上传。")}
      onSubmit={({ text }) => { if (!busy && !disabled && !menuOpen) onSend(text); }}>
      {!!selectedSkills.length && <PromptInputHeader className="flex-wrap px-3 pt-3">{selectedSkills.map(id => <Badge key={id} variant="secondary"><SparklesIcon data-icon="inline-start" />/{id}<Button type="button" variant="ghost" size="icon-xs" aria-label={`移除技能 ${id}`} disabled={busy} onClick={() => onSkillsChange(previous => previous.filter(value => value !== id))}><XIcon /></Button></Badge>)}</PromptInputHeader>}
      <PromptInputBody>
        <PromptInputTextarea ref={inputRef} aria-label="向小马助手提问" placeholder="输入 / 选择技能，或问问业务制度、运营数据…" className="min-h-20 px-4 py-3 text-base"
          aria-expanded={menuOpen} aria-controls={menuOpen ? "chat-skills-menu" : undefined}
          value={draft} onChange={event => { setDismissed(false); setActiveSkill(""); onDraftChange(event.target.value); }}
          onKeyDown={event => {
            if (event.nativeEvent.isComposing) return;
            if (menuOpen && ["ArrowDown", "ArrowUp"].includes(event.key)) {
              event.preventDefault(); const index = selectable.findIndex(item => item.id === activeSkill);
              setActiveSkill(selectable[(index + (event.key === "ArrowDown" ? 1 : -1) + selectable.length) % selectable.length]?.id ?? "");
            } else if (menuOpen && event.key === "Enter" && !event.shiftKey) {
              event.preventDefault(); chooseSkill(activeSkill || selectable[0]?.id || "");
            } else if (menuOpen && event.key === "Escape") { event.preventDefault(); setDismissed(true); }
            else if (busy && event.key === "Enter" && !event.shiftKey) event.preventDefault();
          }} />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <PromptInputButton aria-label="上传文件" tooltip="上传文件" disabled={user?.role !== "admin"} onClick={() => uploadRef.current?.click()}><PlusIcon /></PromptInputButton>
          <Popover>
            <PopoverTrigger asChild><PromptInputButton aria-label="设置 Agent 工具" tooltip="Agent 工具"><WrenchIcon /><span className="hidden sm:inline">Agent 工具</span></PromptInputButton></PopoverTrigger>
            <PopoverContent align="start" sideOffset={8} className="w-64 p-2">
              <FieldGroup className="gap-1">
                <Field orientation="horizontal" className="gap-3 rounded-md px-2 py-2.5"><BookOpenIcon className="size-4 shrink-0 text-muted-foreground" /><FieldLabel htmlFor="chat-knowledge-tool" className="flex-1">知识库检索</FieldLabel><Switch id="chat-knowledge-tool" checked={toolAccess.knowledge} disabled={busy} onCheckedChange={knowledge => onToolAccessChange({ ...toolAccess, knowledge })} /></Field>
                <Field orientation="horizontal" className="gap-3 rounded-md px-2 py-2.5"><DatabaseIcon className="size-4 shrink-0 text-muted-foreground" /><FieldLabel htmlFor="chat-data-tool" className="flex-1">业务数据查询</FieldLabel><Switch id="chat-data-tool" checked={toolAccess.data} disabled={busy} onCheckedChange={data => onToolAccessChange({ ...toolAccess, data })} /></Field>
              </FieldGroup>
            </PopoverContent>
          </Popover>
        </PromptInputTools>
        <div className="flex min-w-0 items-center gap-1">
          {!disabled && <ChatModelSelector value={modelId} onChange={onModelChange} disabled={busy} />}
          <SpeechInput aria-label="语音输入" lang="zh-CN" size="icon-sm" variant="ghost" disabled={busy}
            onSpeechError={code => toast.error(code === "not-allowed" ? "请允许浏览器使用麦克风后重试。" : "语音识别暂不可用，请重试或直接输入文字。")}
            onTranscriptionChange={text => onDraftChange(previous => previous ? `${previous} ${text}` : text)} />
          <PromptInputSubmit className="rounded-full" aria-label={busy ? "停止生成" : "发送问题"}
            status={busy ? "streaming" : "ready"} disabled={disabled || (!busy && !draft.trim())} onStop={onStop} />
        </div>
      </PromptInputFooter>
    </PromptInput>
    </div></PopoverAnchor>
    <PopoverContent side="top" align="start" className="w-[var(--radix-popover-trigger-width)] min-w-72 max-w-[calc(100vw-3rem)] p-1" onOpenAutoFocus={event => event.preventDefault()} onCloseAutoFocus={event => event.preventDefault()}>
      <Command shouldFilter={false} value={activeSkill || selectable[0]?.id || ""} onValueChange={setActiveSkill}>
        <CommandList id="chat-skills-menu" aria-label="选择技能"><CommandEmpty>{skillError || "没有匹配的技能"}</CommandEmpty><CommandGroup heading={selectedSkills.length >= 5 ? "每次最多选择5个技能" : "本轮使用的技能"}>
          {matches.map(skill => <CommandItem key={skill.id} value={skill.id} disabled={!skillAvailable(skill, toolAccess) || selectedSkills.length >= 5} onSelect={chooseSkill}>
            <SparklesIcon /><div className="flex min-w-0 flex-1 flex-col gap-1"><span className="flex gap-2"><span>{skill.name}</span><span className="text-xs text-muted-foreground">/{skill.id}</span></span><span className="line-clamp-2 text-xs text-muted-foreground">{skill.description}</span></div><Badge variant="outline">{!skillAvailable(skill, toolAccess) ? "需开启查询工具" : skill.source === "builtin" ? "内置" : "已上传"}</Badge>
          </CommandItem>)}
        </CommandGroup></CommandList>
      </Command>
    </PopoverContent></Popover>
    {uploadFiles && <UploadDialog open initialFiles={uploadFiles} onOpenChange={open => { if (!open) setUploadFiles(null); }} />}
  </>;
}
