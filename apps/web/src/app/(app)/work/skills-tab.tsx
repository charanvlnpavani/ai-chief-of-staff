"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { GraduationCap, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Private } from "@/components/privacy";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { formatMinutes } from "@/lib/format";
import { qk } from "@/lib/queries";

import { useSkills } from "./use-skills";

type Skill = Schemas["SkillOut"];
type Category = Skill["category"];

const CATEGORIES: { value: Category; label: string }[] = [
  { value: "dsa", label: "DSA" },
  { value: "system_design", label: "System design" },
  { value: "frontend", label: "Frontend" },
  { value: "backend", label: "Backend" },
  { value: "python", label: "Python" },
  { value: "databases", label: "Databases" },
  { value: "ai", label: "AI engineering" },
  { value: "cloud_devops", label: "Cloud & DevOps" },
  { value: "security", label: "Security" },
  { value: "career", label: "Career" },
  { value: "other", label: "Other" },
];
const LEVELS = ["0 · New", "1 · Aware", "2 · Beginner", "3 · Working", "4 · Strong", "5 · Expert"];

function useInvalidateSkills() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: qk.professional });
}

function SkillRow({ skill }: { skill: Skill }) {
  const invalidate = useInvalidateSkills();
  const update = useMutation({
    mutationFn: (body: { level?: number; targetLevel?: number | null }) =>
      unwrap(api.PATCH("/api/v1/professional/skills/{skill_id}", { params: { path: { skill_id: skill.id } }, body })),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/api/v1/professional/skills/{skill_id}", { params: { path: { skill_id: skill.id } } })),
    onSuccess: invalidate,
  });
  const target = skill.targetLevel ?? 5;

  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-2 py-3 sm:grid-cols-[1.5fr_1fr_8rem_8rem_auto]">
      <div className="min-w-0">
        <p className="truncate font-medium">{skill.name}</p>
        <p className="text-xs text-muted-foreground">
          {CATEGORIES.find((c) => c.value === skill.category)?.label} · last 30 days{" "}
          <Private>{formatMinutes(skill.minutesLast30Days ?? 0)}</Private>
        </p>
      </div>
      <Progress value={(skill.level / Math.max(target, 1)) * 100} aria-label={`${skill.name}: level ${skill.level} of target ${target}`} className="hidden sm:block" />
      <Select value={String(skill.level)} onValueChange={(v) => update.mutate({ level: Number(v) })}>
        <SelectTrigger className="w-full" aria-label={`Current level of ${skill.name}`}><SelectValue /></SelectTrigger>
        <SelectContent>
          {LEVELS.map((label, i) => (
            <SelectItem key={label} value={String(i)}>{label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={String(target)} onValueChange={(v) => update.mutate({ targetLevel: Number(v) })}>
        <SelectTrigger className="w-full" aria-label={`Target level of ${skill.name}`}><SelectValue /></SelectTrigger>
        <SelectContent>
          {LEVELS.map((label, i) => (
            <SelectItem key={label} value={String(i)}>Target {label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="ghost" size="icon" aria-label={`Delete ${skill.name}`} onClick={() => remove.mutate()}>
        <Trash2 className="size-4" aria-hidden />
      </Button>
    </li>
  );
}

export function SkillsTab() {
  const invalidate = useInvalidateSkills();
  const skills = useSkills();
  const [name, setName] = useState("");
  const [category, setCategory] = useState<Category>("dsa");

  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/professional/skills", { body: { name: name.trim(), category } })),
    onSuccess: () => {
      setName("");
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Skill matrix</CardTitle>
        <CardDescription>Rate yourself honestly; learning time per skill shows where your effort goes.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <Input aria-label="Skill name" placeholder="e.g. Dynamic programming" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} className="min-w-48 flex-1" />
          <Select value={category} onValueChange={(v) => setCategory(v as Category)}>
            <SelectTrigger className="w-44" aria-label="Category"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => (
                <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="submit" disabled={!name.trim() || create.isPending}>
            <Plus className="size-4" aria-hidden /> Add skill
          </Button>
        </form>
        {skills.isPending ? (
          <LoadingRows />
        ) : skills.isError ? (
          <ErrorState error={skills.error} onRetry={() => skills.refetch()} />
        ) : skills.data.length === 0 ? (
          <EmptyState icon={GraduationCap} title="No skills tracked yet" description="Add the skills you are building, such as DSA, system design or React." />
        ) : (
          <ul className="divide-y">
            {skills.data.map((skill) => (
              <SkillRow key={skill.id} skill={skill} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
