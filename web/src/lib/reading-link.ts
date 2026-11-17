/** Ссылка «продолжить чтение» по типу источника (B-012):
 *  книга → PDF-ридер (с местом чтения, если есть), видео/статья → текущая глава,
 *  без глав или неизвестный тип → страница источника. Одна функция для «Сегодня»
 *  и курс-доски — без дублирования правил. */

export type ReadingTarget = {
  sourceUid: string;
  kind?: string | null;
  chapter?: number | null;
  page?: number | null;
  totalChapters?: number | null;
};

export function readingHref(t: ReadingTarget): string {
  if (!t.kind) return `/library/${t.sourceUid}`; // тип неизвестен — не гадаем, открываем источник
  if (t.kind === "book") {
    const ch = t.chapter && t.chapter > 0 ? `?ch=${t.chapter}` : "";
    const pg = t.page && t.page > 0 && ch ? `&page=${t.page}` : "";
    return `/library/${t.sourceUid}/read${ch}${pg}`;
  }
  // totalChapters не задан — главам курса доверяем; 0 = глав нет → страница источника
  const hasChapters = t.totalChapters == null || t.totalChapters > 0;
  if (hasChapters && t.chapter && t.chapter > 0) return `/library/${t.sourceUid}/${t.chapter}`;
  return `/library/${t.sourceUid}`;
}
