"use client";

/** Редактор профиля: машины и предпочтения обучения. */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { Profile } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ProfileForm({ initial }: { initial: Profile }) {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile>(initial);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const res = await fetch("/api/settings/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      if (!res.ok) throw new Error(String(res.status));
      toast.success("Профиль сохранён");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  };

  const setMachine = (id: string, patch: Partial<Profile["machines"][number]>) => {
    setProfile((p) => ({ ...p, machines: p.machines.map((m) => (m.id === id ? { ...m, ...patch } : m)) }));
  };

  return (
    <div className="flex flex-col gap-8">
      <section className="grid gap-5 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="p-name">Имя</Label>
          <Input id="p-name" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="p-about">О себе</Label>
          <Input id="p-about" value={profile.about} onChange={(e) => setProfile({ ...profile, about: e.target.value })} />
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h3 className="text-sm font-medium text-muted-foreground">Машины (для практики)</h3>
        {profile.machines.map((m) => (
          <div key={m.id} className="grid gap-3 rounded-xl border bg-background/50 p-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Имя</Label>
              <Input value={m.name} onChange={(e) => setMachine(m.id, { name: e.target.value })} aria-label={`Имя машины ${m.id}`} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Характеристики</Label>
              <Input value={m.specs} onChange={(e) => setMachine(m.id, { specs: e.target.value })} aria-label={`Характеристики ${m.id}`} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Инструменты (через запятую)</Label>
              <Input
                value={m.tools.join(", ")}
                onChange={(e) => setMachine(m.id, { tools: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })}
                aria-label={`Инструменты ${m.id}`}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Заметки</Label>
              <Input value={m.notes} onChange={(e) => setMachine(m.id, { notes: e.target.value })} aria-label={`Заметки ${m.id}`} />
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-5 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="p-min">Сессия, мин</Label>
          <Input
            id="p-min"
            type="number"
            value={profile.learning.session_minutes}
            onChange={(e) => setProfile({ ...profile, learning: { ...profile.learning, session_minutes: Number(e.target.value) } })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="p-concepts">Понятий в теории</Label>
          <Input
            id="p-concepts"
            type="number"
            value={profile.learning.theory_concepts}
            onChange={(e) => setProfile({ ...profile, learning: { ...profile.learning, theory_concepts: Number(e.target.value) } })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="p-style">Стиль объяснений</Label>
          <Input
            id="p-style"
            value={profile.learning.explain_style}
            onChange={(e) => setProfile({ ...profile, learning: { ...profile.learning, explain_style: e.target.value } })}
          />
        </div>
      </section>

      <div>
        <Button onClick={save} disabled={busy}>
          {busy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
          Сохранить профиль
        </Button>
      </div>
    </div>
  );
}
