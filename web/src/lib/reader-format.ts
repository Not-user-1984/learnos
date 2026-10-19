/** Пост-обработка текста главы для читалки: подглавы-«голые строки» → markdown-заголовки.
 *
 *  PDF-сплиттер сохраняет подглавы обычными строками между пустыми (без ##),
 *  поэтому в рендере всё сливается в один шрифт. Здесь превращаем их в `##`.
 */

const MAX_HEADING = 64;

function isBlank(line: string): boolean {
  return line.trim() === "";
}

function looksLikeHeading(line: string): boolean {
  const s = line.trim();
  if (s.length < 3 || s.length > MAX_HEADING) return false;
  if (/^(#{1,6}|>|\||[-*+]\s|\d+[.)]\s|```|\|)/.test(s)) return false; // уже markdown или список
  if (/[.,;!?»)]$/.test(s)) return false; // предложение, не заголовок
  if (/\s\d{1,4}$/.test(s)) return false; // колонтитул с номером страницы («… 23»)
  if (!/^[«"A-ZА-ЯЁ0-9]/.test(s)) return false; // начинается с заглавной/цифры/кавычки
  return true;
}

export function formatChapter(text: string, chapterTitle?: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  // дублирующий заголовок главы из текста («# 2. Микросервисы») — наш h1 уже нарисован
  let start = 0;
  const first = lines[0]?.trim() ?? "";
  if (first.startsWith("# ")) {
    const body = first.slice(2).replace(/^\d+[.)]\s*/, "").trim();
    const ref = (chapterTitle ?? "").trim();
    if (!ref || body === ref || ref.startsWith(body) || body.startsWith(ref)) {
      start = 1;
    }
  }
  for (let i = start; i < lines.length; i++) {
    const line = lines[i];
    if (
      looksLikeHeading(line) &&
      (isBlank(lines[i - 1] ?? "") || i === start) &&
      isBlank(lines[i + 1] ?? "")
    ) {
      out.push(`## ${line.trim()}`);
    } else {
      out.push(line);
    }
  }
  return out.join("\n");
}
