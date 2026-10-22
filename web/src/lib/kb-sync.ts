/** Синхронизация свежести списка /kb: мутации категорий происходят на других страницах
 *  (/kb/[uid], входящие), а возврат на /kb может прийти из кэша роутера — ставим dirty-флаг,
 *  клиент /kb при монтировании его подхватывает и обновляет список. */

const DIRTY_KEY = "learnos-kb-list-dirty";

/** Пометить список /kb устаревшим — вызвать после успешной мутации категории блока. */
export function markKbListDirty(): void {
  localStorage.setItem(DIRTY_KEY, "1");
}

/** Снять флаг, если он стоял; возвращает true, когда список /kb нужно обновить. */
export function consumeKbListDirty(): boolean {
  if (typeof window === "undefined" || localStorage.getItem(DIRTY_KEY) !== "1") return false;
  localStorage.removeItem(DIRTY_KEY);
  return true;
}
