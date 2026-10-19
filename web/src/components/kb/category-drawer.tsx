"use client";

/** Категории для узких экранов (планшет/телефон): кнопка + диалог с деревом. */

import { useState } from "react";
import { FolderTree } from "lucide-react";
import type { CategoryNode } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CategoryTree } from "./category-tree";

export function CategoryDrawer({
  nodes,
  active,
}: {
  nodes: CategoryNode[];
  active: string | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="outline" size="sm" className="lg:hidden" onClick={() => setOpen(true)}>
        <FolderTree className="mr-1 h-4 w-4" /> Категории{active ? `: ${active.split("/").pop()}` : ""}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80dvh] overflow-y-auto sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Категории</DialogTitle>
          </DialogHeader>
          <div onClick={() => setOpen(false)}>
            <CategoryTree nodes={nodes} active={active} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
