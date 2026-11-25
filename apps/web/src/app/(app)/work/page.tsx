"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { PageHeader } from "@/components/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { LearningTab } from "./learning-tab";
import { PracticeTab } from "./practice-tab";
import { SkillsTab } from "./skills-tab";

const TABS = ["learning", "practice", "skills"] as const;
type Tab = (typeof TABS)[number];

function WorkTabs() {
  const params = useSearchParams();
  const router = useRouter();
  const requested = params.get("tab");
  const tab: Tab = TABS.includes(requested as Tab) ? (requested as Tab) : "learning";

  return (
    <Tabs value={tab} onValueChange={(value) => router.replace(`/work?tab=${value}`, { scroll: false })}>
      <TabsList className="mb-4">
        <TabsTrigger value="learning">Learning</TabsTrigger>
        <TabsTrigger value="practice">DSA practice</TabsTrigger>
        <TabsTrigger value="skills">Skills</TabsTrigger>
      </TabsList>
      <TabsContent value="learning">
        <LearningTab />
      </TabsContent>
      <TabsContent value="practice">
        <PracticeTab />
      </TabsContent>
      <TabsContent value="skills">
        <SkillsTab />
      </TabsContent>
    </Tabs>
  );
}

export default function WorkPage() {
  return (
    <>
      <PageHeader
        title="Work & learning"
        description="Your daily learning goal, DSA practice with spaced review, and skill levels."
      />
      <Suspense fallback={null}>
        <WorkTabs />
      </Suspense>
    </>
  );
}
