"use client";

import { useState } from "react";
import { CheckIcon, ChevronDownIcon } from "lucide-react";
import { ModelSelector, ModelSelectorContent, ModelSelectorEmpty, ModelSelectorGroup, ModelSelectorInput, ModelSelectorItem, ModelSelectorList, ModelSelectorName, ModelSelectorTrigger } from "@/components/ai-elements/model-selector";
import { PromptInputButton } from "@/components/ai-elements/prompt-input";

import { useWorkspace } from "@/lib/services/provider";

export function ChatModelSelector({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const { models: chatModels } = useWorkspace();
  const selected = chatModels.find(model => model.id === value) ?? chatModels[0];
  if (!selected) return <PromptInputButton disabled>模型加载中</PromptInputButton>;
  return <ModelSelector open={open} onOpenChange={setOpen}>
    <ModelSelectorTrigger asChild><PromptInputButton aria-label={`当前模型：${selected.name}`} className="max-w-32 sm:max-w-44" size="sm" tooltip="选择模型" disabled={disabled}><span className="truncate">{selected.name}</span><ChevronDownIcon data-icon="inline-end" /></PromptInputButton></ModelSelectorTrigger>
    <ModelSelectorContent title="选择模型">
      <ModelSelectorInput placeholder="搜索模型" />
      <ModelSelectorList><ModelSelectorEmpty>没有匹配的模型</ModelSelectorEmpty><ModelSelectorGroup>
        {chatModels.map(model => <ModelSelectorItem key={model.id} value={model.name} onSelect={() => { onChange(model.id); setOpen(false); }}><ModelSelectorName>{model.name}{model.profile.max_input_tokens ? ` · ${model.profile.max_input_tokens >= 1000000 ? `${model.profile.max_input_tokens / 1000000}M` : `${Math.round(model.profile.max_input_tokens / 1000)}k`}` : ""}</ModelSelectorName>{selected.id === model.id && <CheckIcon className="ml-auto" />}</ModelSelectorItem>)}
      </ModelSelectorGroup></ModelSelectorList>
    </ModelSelectorContent>
  </ModelSelector>;
}
