"use client";

/** Создание курса: вручную (topic) или план агентом (topic → course_planner). */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Checkbox } from "@/components/ui/checkbox";

type PlanItem = { item_type: string; title: string; source_uid?: string; chapter?: number; block_uid?: string; url?: string; note?: string };
type Plan = { title: string; topic: string; description: string; category?: string; items: PlanItem[] };

export function NewCourseButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [picked, setPicked] = useState<Record<number, boolean>>({});

  const planCourse = async () => {
    setBusy(true);
    try {
      const p = await apiPost<Plan>("/courses/plan", { topic });
      setPlan(p);
      setPicked(Object.fromEntries(p.items.map((_: PlanItem, i: number) => [i, true])));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "планировщик не смог");
    } finally {
      setBusy(false);
    }
  };

  const createFromPlan = async () => {
    if (!plan) return;
    setBusy(true);
    try {
      const items = plan.items.filter((_, i) => picked[i]);
      const course = await apiPost<{ uid: string }>("/courses/from-plan", { plan: { ...plan, items } });
      toast.success("Курс создан");
      setOpen(false);
      router.push(`/courses/${course.uid}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  };

  const createManual = async () => {
    setBusy(true);
    try {
      const course = await apiPost<{ uid: string }>("/courses", { topic, title: topic });
      setOpen(false);
      router.push(`/courses/${course.uid}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <Icon name="add" size={16} /> Новый курс
      </DialogTrigger>
      <DialogContent className="max-h-[80dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Новый курс</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="agent">
          <TabsList>
            <TabsTrigger value="agent">Собрать агентом</TabsTrigger>
            <TabsTrigger value="manual">Вручную</TabsTrigger>
          </TabsList>
          <TabsContent value="agent" className="flex flex-col gap-3 pt-3">
            <div className="flex gap-2">
              <Input placeholder="Тема: например, Kubernetes на хомлабе" value={topic} onChange={(e) => setTopic(e.target.value)} />
              <Button disabled={!topic.trim() || busy} onClick={planCourse}>
                Собрать план
              </Button>
            </div>
            {plan && (
              <div className="flex flex-col gap-2">
                <p className="text-sm font-medium">{plan.title}</p>
                {plan.description && <p className="text-sm text-muted-foreground">{plan.description}</p>}
                {plan.items.map((item, i) => (
                  <label key={i} className="flex items-start gap-2 rounded-lg border p-2 text-sm">
                    <Checkbox
                      checked={picked[i] ?? false}
                      onCheckedChange={(v) => setPicked((p) => ({ ...p, [i]: v === true }))}
                    />
                    <span>
                      <b>{item.title}</b> <span className="text-muted-foreground">({item.item_type})</span>
                      {item.note && <span className="block text-xs text-muted-foreground">{item.note}</span>}
                    </span>
                  </label>
                ))}
                <Button disabled={busy} onClick={createFromPlan}>
                  Создать курс из выбранного
                </Button>
              </div>
            )}
          </TabsContent>
          <TabsContent value="manual" className="flex flex-col gap-3 pt-3">
            <Input placeholder="Тема курса" value={topic} onChange={(e) => setTopic(e.target.value)} />
            <Button disabled={!topic.trim() || busy} onClick={createManual}>
              Создать пустой курс
            </Button>
            <p className="text-xs text-muted-foreground">Элементы добавишь на странице курса из библиотеки и базы знаний.</p>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

