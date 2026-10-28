"use client";

/** Кот-питомец чата: гуляет по нижней полке области сообщений и бросает фразы
 *  по клику. Спрайт oneko.gif (256×128, кадры 32×32) и карта кадров — из
 *  oneko.js (https://github.com/adryd325/oneko.js, MIT); координаты клеток
 *  соответствуют spriteSets оригинала: idle/alert/scratch/sleep и бег E
 *  (влево — зеркалим scaleX(-1), как кадры W оригинала).
 *  Рендерится только в чате (ChatStart и ChatView): absolute-оверлей над
 *  скролл-контейнером, клики проходят везде, кроме самого кота. */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/utils";

/** Фразы кота в пузыре. Пополняется без логики. */
const CAT_PHRASES = [
  "Мы чё там, пиздюк, изучаем?",
  "Давай грохнем алгоритмы",
  "Почитаем Кнута, долбоёб?",
  "Сессия сама себя не пройдёт",
  "Опять прокрастинация? Я одного мурчания от разочарования",
  "Забей: я посплю на твоих незакреплённых блоках",
  "Ты учишь — я гуляю. Deal.",
  "Мурчание на частоте закрепления памяти",
  "Фейнман бы одобрил. Я — посмотрю",
  "Курсы сами себя не соберутся, кстати",
  "Я бы помог, но я кот",
  "Ещё одна глава — и полежим",
];

/** Кадры спрайта oneko: [x, y] в клетках 32×32 → background-position = координата × 32. */
const FRAMES = {
  idle: [[-3, -3]],
  alert: [[-7, -3]],
  walk: [
    [-3, 0],
    [-3, -1],
  ], // бег вправо (набор «E» оригинала); влево — scaleX(-1)
  scratch: [
    [-5, 0],
    [-6, 0],
    [-7, 0],
  ],
  sleep: [
    [-2, 0],
    [-2, -1],
  ],
} as const;

type Phase = keyof typeof FRAMES;

const TICK_MS = 125; // ~8 fps, как у оригинального oneko
const WALK_SPEED = 9; // px за тик ≈ 70 px/s — прогулочный шаг по полке
const BUBBLE_MS = 3000; // пузырь фразы висит 3 с
const EDGE = 8; // отступ от краёв полки, px

const STORAGE_KEY = "learnos:cat";

/** Видимость кота — client-only значение из localStorage, читается через
 *  useSyncExternalStore; запись рассылает подписчиков вручную (storage-событие
 *  в том же табе не срабатывает). */
const catListeners = new Set<() => void>();
const subscribeCat = (cb: () => void) => {
  catListeners.add(cb);
  return () => {
    catListeners.delete(cb);
  };
};
const readCatVisible = () => localStorage.getItem(STORAGE_KEY) !== "off";
const writeCatVisible = (visible: boolean) => {
  localStorage.setItem(STORAGE_KEY, visible ? "on" : "off");
  catListeners.forEach((l) => l());
};

const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";
const subscribeReduced = (cb: () => void) => {
  const mq = window.matchMedia(REDUCED_QUERY);
  mq.addEventListener("change", cb);
  return () => {
    mq.removeEventListener("change", cb);
  };
};

/** Следующий отрезок жизни кота: идёт 1–4 с, чаще просто сидит, изредка чешется или спит. */
function nextPhase(): { phase: Exclude<Phase, "alert">; dir: 1 | -1; duration: number } {
  const roll = Math.random();
  if (roll < 0.55) {
    return { phase: "walk", dir: Math.random() < 0.5 ? 1 : -1, duration: 1000 + Math.random() * 3000 };
  }
  if (roll < 0.8) return { phase: "idle", dir: 1, duration: 2000 + Math.random() * 3000 };
  if (roll < 0.9) return { phase: "scratch", dir: 1, duration: 1200 + Math.random() * 800 };
  return { phase: "sleep", dir: 1, duration: 3000 + Math.random() * 4000 };
}

export function ChatCat() {
  const [view, setView] = useState({ left: 64, bg: "-96px -96px", flip: false });
  const [bubble, setBubble] = useState<string | null>(null);
  const [width, setWidth] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const visible = useSyncExternalStore(subscribeCat, readCatVisible, () => true);
  // prefers-reduced-motion: кот сидит без ходьбы, фразы по клику остаются
  const reduced = useSyncExternalStore(
    subscribeReduced,
    () => window.matchMedia(REDUCED_QUERY).matches,
    () => false,
  );

  // машина состояний в refs: тик меняет только собственный снапшот setView,
  // лента сообщений не ре-рендерится
  const phase = useRef<Exclude<Phase, "alert">>("idle");
  const phaseEnd = useRef(0);
  const dir = useRef<1 | -1>(1);
  const frame = useRef(0);
  const x = useRef(64);
  const bubbleUntil = useRef(0);
  const lastPhrase = useRef(0);

  // ширина полки = ширина контейнера-родителя (скролл-область сообщений)
  useEffect(() => {
    const el = rootRef.current?.parentElement;
    if (!el) return;
    const update = () => setWidth(el.offsetWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || reduced || width === 0) return;
    const id = setInterval(() => {
      const now = Date.now();
      if (now >= phaseEnd.current) {
        const next = nextPhase();
        phase.current = next.phase;
        dir.current = next.dir;
        phaseEnd.current = now + next.duration;
      }
      if (phase.current === "walk") {
        x.current += dir.current * WALK_SPEED;
        const bound = Math.max(EDGE, width - 32 - EDGE);
        if (x.current <= EDGE) {
          x.current = EDGE;
          dir.current = 1;
        } else if (x.current >= bound) {
          x.current = bound;
          dir.current = -1;
        }
      }
      frame.current += 1;
      const set = now < bubbleUntil.current ? FRAMES.alert : FRAMES[phase.current];
      const [fx, fy] = set[frame.current % set.length];
      setView((prev) => {
        const left = x.current;
        const bg = `${fx * 32}px ${fy * 32}px`;
        const flip = dir.current < 0;
        return prev.left === left && prev.bg === bg && prev.flip === flip ? prev : { left, bg, flip };
      });
    }, TICK_MS);
    return () => clearInterval(id);
  }, [visible, reduced, width]);

  // пузырь гаснет таймером — работает и в reduced-motion, где тика нет
  useEffect(() => {
    if (!bubble) return;
    const t = setTimeout(() => setBubble(null), BUBBLE_MS);
    return () => clearTimeout(t);
  }, [bubble]);

  const speak = () => {
    let i = Math.floor(Math.random() * CAT_PHRASES.length);
    if (i === lastPhrase.current) i = (i + 1) % CAT_PHRASES.length;
    lastPhrase.current = i;
    bubbleUntil.current = Date.now() + BUBBLE_MS;
    // на время фразы кот садится и смотрит (кадр alert в тике)
    phase.current = "idle";
    phaseEnd.current = bubbleUntil.current;
    setBubble(CAT_PHRASES[i]);
  };

  const toggle = () => writeCatVisible(!visible);

  const bubbleAtRight = view.left > width - 220;

  return (
    <div ref={rootRef} className="pointer-events-none absolute inset-x-0 bottom-0 z-10">
      <button
        type="button"
        onClick={toggle}
        aria-label={visible ? "Скрыть кота" : "Показать кота"}
        className="pointer-events-auto absolute bottom-2 right-2 z-20 rounded-lg border bg-card/80 p-1.5 text-muted-foreground shadow-sm backdrop-blur transition hover:text-foreground"
      >
        <Icon name="pets" size={14} />
      </button>
      {visible && (
        <div className="absolute bottom-2" style={{ left: view.left }}>
          {bubble && (
            <div
              className={cn(
                "absolute bottom-full mb-1 w-max max-w-56 rounded-xl border bg-card px-2.5 py-1.5 text-xs text-foreground shadow-sm",
                bubbleAtRight ? "right-0" : "left-0",
              )}
            >
              {bubble}
            </div>
          )}
          <button
            type="button"
            onClick={speak}
            aria-label="Погладить кота"
            className="block h-8 w-8 cursor-pointer [image-rendering:pixelated]"
            style={{
              backgroundImage: "url(/oneko.gif)",
              backgroundPosition: view.bg,
              transform: view.flip ? "scaleX(-1)" : undefined,
            }}
          />
        </div>
      )}
    </div>
  );
}
