# Дизайн-система LearnOS (web)

Единый источник правды по дизайну интерфейса. Всё, что ниже — обязательные правила для новых экранов и правок.

## Темы

Три темы, переключаются циклом «тёмная → пергамент → светлая» кнопкой в сайдбаре (`components/theme-toggle.tsx`). **Пергамент — тема по умолчанию.**

Реализация: `next-themes` c `attribute="class"` — на `<html>` вешается класс `dark` / `parchment` / ничего (light = `:root`). Все палитры лежат в `src/app/globals.css` в oklch:

| Блок | Тема |
|---|---|
| `:root` | светлая |
| `.dark` | тёмная (индиго-графит, фиолетовый акцент) |
| `.parchment` | пергамент: тёплая бумага, сепия, охра-акцент |

Менять цвета — только в этих трёх блоках переменных, не в компонентах.

### Правило токенов (главное)

В компонентах **запрещено хардкодить hue-цвета** (`violet-500`, `sky-500/20`, …). Только семантические классы:

- акцент/ссылки/активное: `text-primary`, `bg-primary/15`, `border-primary/40`, `hover:border-primary/50`
- поверхности: `bg-card`, `bg-muted`, `border-border`
- текст: `text-foreground`, `text-muted-foreground`

Тогда одна и та же кнопка в тёмной теме фиолетовая, а в пергаменте — тёплая охра (история: фиолет b=−61 в LAB конфликтует с тёплой бумагой b≈+20).

Допустимые исключения: светофор статусов (`emerald/amber/rose`) и градиентные метки категорий (`kb/category-tree.tsx`).

### Специфика пергамента (CSS в globals.css)

- весь интерфейс — книжный serif (Literata), заголовки тоже;
- зерно бумаги: SVG-текстура (feTurbulence) в `background-image` у `body`;
- сепия для markdown: `html.parchment .prose { --tw-prose-*: … }` — переопределяет `prose-zinc`;
- баблы сообщений пользователя: `html.parchment .user-bubble` — светлая песочная плашка с тёмным текстом (класс `user-bubble` на бабле в `chat-view.tsx`); в dark/light работает `bg-primary text-primary-foreground`;
- код-блоки остаются тёмными во всех темах («чернильница»).

## Иконки

**Material Symbols Rounded** (стилистика Pixel/Android) — переменный шрифт, self-host из npm-пакета `material-symbols` (`@import "material-symbols/rounded.css"` в globals.css).

Компонент — `src/components/ui/icon.tsx`:

```tsx
import { Icon } from "@/components/ui/icon";

<Icon name="check" size={16} />              {/* обычный контур */}
<Icon name="school" size={20} filled />      {/* залитый — активные состояния */}
```

- имена — snake_case с официального каталога (fonts.google.com/icons): `chat`, `psychology`, `auto_stories`, `progress_activity` (спиннер, вешать `animate-spin`)…
- размер — только через `size={px}`, не классами `h-4 w-4`;
- в навигации активный пункт получает `filled`;
- **никаких lucide-react и эмодзи в UI** (выпилены 2026-10-22);
- имена глифов для типов источников и режимов чата: `kindIcon()` / `modeIcon()` в `lib/format.ts`.

Проверить, существует ли глиф в шрифте (для новых имён):

```bash
cd web && uvx --from fonttools --with brotli python -c "
from fontTools.ttLib import TTFont
f = TTFont('node_modules/material-symbols/material-symbols-rounded.woff2')
names = {n for t in f['cmap'].tables for n in t.cmap.values()}
print('check' in ' '.join(names))"  # ищем вхождение имени
```

## Шрифты

| Переменная | Шрифт | Откуда | Где |
|---|---|---|---|
| `--font-sans` | Inter (cyrillic) | `next/font/google` | `layout.tsx` — весь UI в dark/light |
| `--font-geist-mono` | JetBrains Mono (cyrillic) | `next/font/google` | код |
| `--font-serif` | Literata Variable (cyrillic) | npm `@fontsource-variable/literata`, `opsz.css` | пергамент (весь UI) и читалка (семья «Книжный») |

next/font для Literata не используется (баг сборки) — не переводить обратно.

## Приёмы

- Markdown-контент: `components/markdown/Markdown.tsx`, цитаты `prose-blockquote:border-primary/60`, инлайн-код — семантические токены.
- Тумблер тем: карты `NEXT/GLYPH/TITLE` в `theme-toggle.tsx` — при добавлении темы обновить все три и `themes=[...]` в `layout.tsx`.
- Sonner-тосты и mermaid мапят parchment → светлую тему (`ui/sonner.tsx`, `Mermaid.tsx`).

## Проверка перед коммитом

```bash
cd web && npm run lint && npx tsc --noEmit && npm run build
grep -rn "violet\|purple\|fuchsia\|lucide-react" src/   # должно быть пусто
```

Визуально: прогнать экран в тёмной и пергаменте (кнопка темы), планшет 810px.
