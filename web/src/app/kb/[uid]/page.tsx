/** Страница блока: метаданные + MD-тело + версии. */

import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { BlockDetail } from "@/lib/types";
import { BlockPageClient } from "@/components/kb/block-page-client";

export const dynamic = "force-dynamic";

export default async function BlockPage({ params }: { params: Promise<{ uid: string }> }) {
  const { uid } = await params;
  let block: BlockDetail;
  let versions: { version: number; reason: string | null; conversation_uid: string | null; created_at: string; size: number }[] = [];
  try {
    block = await api<BlockDetail>(`/kb/blocks/${uid}`);
    versions = await api<typeof versions>(`/kb/blocks/${uid}/versions`).catch(() => []);
  } catch {
    notFound();
  }
  return <BlockPageClient block={block} versions={versions} />;
}
