"use client";

import { Badge } from "@/components/ui/badge";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { ChunkConfiguration as Configuration } from "@/lib/services/contracts";

export function ChunkConfigurationFields({ value, onChange, prefix = "chunk" }: { value: Configuration; onChange: (value: Configuration) => void; prefix?: string }) {
  return <FieldGroup>
    <Field>
      <FieldLabel>分块方式 <Badge variant="secondary">结构保留</Badge></FieldLabel>
      <FieldDescription>按标题与段落组织内容，表格、公式与附属说明保持完整。</FieldDescription>
    </Field>
    <Field>
      <FieldLabel htmlFor={`${prefix}-length`}>目标长度</FieldLabel>
      <Input id={`${prefix}-length`} type="number" min={100} max={12000} step={100}
        value={value.targetLength} onChange={event => onChange({ ...value, targetLength: Number(event.target.value) })} />
      <FieldDescription>100–12,000 字符，用于组合相邻内容块。</FieldDescription>
    </Field>
    <FieldGroup className="grid grid-cols-2 gap-4">
      <Field>
        <FieldLabel htmlFor={`${prefix}-min`}>最小长度</FieldLabel>
        <Input id={`${prefix}-min`} type="number" min={0} max={value.targetLength} value={value.minLength}
          onChange={event => onChange({ ...value, minLength: Number(event.target.value) })} />
        <FieldDescription>避免生成过短分块</FieldDescription>
      </Field>
      <Field>
        <FieldLabel htmlFor={`${prefix}-max`}>最大长度</FieldLabel>
        <Input id={`${prefix}-max`} type="number" min={value.targetLength} max={20000} value={value.maxLength}
          onChange={event => onChange({ ...value, maxLength: Number(event.target.value) })} />
        <FieldDescription>完整结构单元允许超长</FieldDescription>
      </Field>
    </FieldGroup>
  </FieldGroup>;
}

export function validConfiguration(value: Configuration) {
  return [value.targetLength, value.minLength, value.maxLength].every(Number.isInteger)
    && value.minLength >= 0 && value.minLength <= value.targetLength
    && value.targetLength >= 100 && value.targetLength <= 12000
    && value.maxLength >= value.targetLength && value.maxLength <= 20000;
}
