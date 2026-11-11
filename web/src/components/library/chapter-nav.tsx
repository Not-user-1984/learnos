/** Навигация «предыдущая/следующая глава» (B-009: единый компонент вместо трёх копий). */

import Link from "next/link";
import { Icon } from "@/components/ui/icon";

export function ChapterNav({
  href,
  prevIdx,
  nextIdx,
  pdf,
}: {
  href: (idx: number) => string;
  prevIdx: number | null;
  nextIdx: number | null;
  pdf?: boolean;
}) {
  return (
    <nav className={`mx-auto flex max-w-2xl items-center justify-between border-t px-5 py-5 sm:px-8 ${pdf ? "print:hidden" : ""}`}>
      {prevIdx ? (
        <Link
          href={href(prevIdx)}
          className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
        >
          <Icon name="chevron_left" size={16} /> Глава {prevIdx}
        </Link>
      ) : (
        <span />
      )}
      {nextIdx && (
        <Link
          href={href(nextIdx)}
          className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
        >
          Глава {nextIdx} <Icon name="chevron_right" size={16} />
        </Link>
      )}
    </nav>
  );
}
