/** Библиотека: витрина источников с вкладками по типам. */

import { api } from "@/lib/api";
import type { SourceCard } from "@/lib/types";
import { AddSourceButton } from "@/components/library/upload-dialog";
import { LibraryBrowser } from "@/components/library/library-browser";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const sources = await api<SourceCard[]>("/sources").catch(() => [] as SourceCard[]);
  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Библиотека</h1>
          <p className="text-sm text-muted-foreground">Книги, видео и статьи — всё, из чего рождается знание</p>
        </div>
        <AddSourceButton />
      </header>
      <LibraryBrowser sources={sources} />
    </div>
  );
}
