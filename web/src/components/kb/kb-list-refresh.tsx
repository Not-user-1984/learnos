"use client";

/** Тихий компонент на /kb: если категории блоков менялись на другой странице —
 *  при монтировании списка обновляет маршрут, чтобы карточки и бейджи были свежими. */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { consumeKbListDirty } from "@/lib/kb-sync";

export function KbListRefresh() {
  const router = useRouter();
  useEffect(() => {
    if (consumeKbListDirty()) router.refresh();
  }, [router]);
  return null;
}
