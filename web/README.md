# LearnOS Web

Next.js (App Router) + TS strict + Tailwind 4 + shadcn-подход. PWA.

## Запуск

```bash
npm install
npm run dev        # dev-сервер, API по умолчанию http://localhost:8765 (LEARNOS_API_URL)
npm run build && npm start
```

Проверки: `npm run lint && npx tsc --noEmit && npm run build`; типы API — `npm run gen:api`.

## Документация

- **[DESIGN.md](DESIGN.md) — дизайн-система: темы (пергамент/тёмная/светлая), Material Symbols Rounded, шрифты, правило токенов.** Читать перед любыми правками UI.
