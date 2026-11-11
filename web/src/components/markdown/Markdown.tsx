/** Единый рендер Markdown (блоки, главы, чат): GFM, alerts, KaTeX, wikilinks, mermaid. */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkAlerts from "remark-github-blockquote-alert";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { ActionLink } from "./ActionLink";
import { CodeBlock } from "./CodeBlock";

type Props = {
  content: string;
  /** uid → заголовок для рендера [[blk_…]] */
  linkTitles?: Record<string, string>;
  /** Клик по таймкоду [мм:сс] (панель видео, B-006): seek плеера. */
  onTimecode?: (seconds: number) => void;
  className?: string;
};

/** Заменяет [[blk_x]] на Markdown-ссылки (до рендера). */
function wikilinks(content: string, titles: Record<string, string>): string {
  return content.replace(/\[\[(blk_[0-9a-f]+)\]\]/g, (_all, uid: string) => {
    const title = titles[uid] ?? uid;
    return `[${title}](/kb/${uid})`;
  });
}

/** [мм:сс] / [ч:мм:сс] → ссылка #t=сек (до рендера; активна при onTimecode). */
function timecodes(content: string): string {
  return content.replace(
    /\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g,
    (whole, stamp: string) => {
      const parts = stamp.split(":").map(Number);
      const secs =
        parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : parts[0] * 60 + parts[1];
      return Number.isFinite(secs) ? `[${stamp}](#t=${Math.floor(secs)})` : whole;
    },
  );
}

export function Markdown({ content, linkTitles = {}, onTimecode, className = "" }: Props) {
  return (
    <div
      className={`prose prose-zinc dark:prose-invert max-w-none
        prose-headings:mt-8 prose-headings:mb-3 prose-headings:font-semibold
        prose-p:leading-[1.75] prose-li:leading-[1.75] prose-ul:my-3 prose-ol:my-3
        prose-table:my-4 prose-blockquote:my-4 prose-blockquote:border-primary/60
        prose-hr:my-8 ${className}`}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkAlerts, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // http(s)-ссылки: обычные остаются ссылками, YouTube/PDF получают меню действий;
          // #t=сек — таймкод видео: кнопкой на seek плеера (B-006)
          a({ href, children }) {
            if (onTimecode && href?.startsWith("#t=")) {
              const secs = Number(href.slice(3));
              return (
                <button
                  type="button"
                  onClick={() => onTimecode(secs)}
                  className="rounded-md border border-primary/40 bg-primary/10 px-1.5 py-0.5 font-mono text-[0.85em] text-primary transition hover:bg-primary/20"
                >
                  {children}
                </button>
              );
            }
            return <ActionLink href={href}>{children}</ActionLink>;
          },
          pre({ children }) {
            // достаём текст и язык из вложенного <code class="language-x">
            const raw: unknown = Array.isArray(children) ? children[0] : children;
            const child = raw as React.ReactElement<{ className?: string; children?: React.ReactNode }> | undefined;
            const cls = child?.props?.className ?? "";
            const lang = /language-(\w+)/.exec(cls)?.[1];
            const text = extractText(child?.props?.children ?? "");
            return (
              <CodeBlock language={lang} code={text}>
                {children}
              </CodeBlock>
            );
          },
          code({ className: cls, children, ...props }) {
            const text = String(children ?? "");
            const isBlock = cls?.startsWith("language-") || text.includes("\n");
            if (!isBlock) {
              return (
                <code
                  className="rounded-md border border-border/60 bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-primary"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            // блоки (включая mermaid) рисует CodeBlock из pre-рендерера
            return (
              <code className={`${cls ?? ""} font-mono`} {...props}>
                {children}
              </code>
            );
          },
          // картинки глав книг (/api/sources/…/images/…) — рендер по центру, в пределах колонки
          img({ src, alt }) {
            return (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={typeof src === "string" ? src : ""}
                alt={alt ?? ""}
                loading="lazy"
                className="mx-auto my-4 h-auto max-w-full rounded-lg border"
              />
            );
          },
        }}
      >
        {wikilinks(onTimecode ? timecodes(content) : content, linkTitles)}
      </ReactMarkdown>
    </div>
  );
}

function extractText(node: React.ReactNode): string {
  if (node === null || node === undefined) return "";
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in (node as React.ReactElement)) {
    return extractText((node as React.ReactElement<{ children?: React.ReactNode }>).props.children);
  }
  return "";
}
