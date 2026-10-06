import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Mermaid } from "./Mermaid";

export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown-body text-[15px] leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h1 className="mb-3 mt-6 text-2xl font-bold first:mt-0" {...p} />,
          h2: (p) => <h2 className="mb-2 mt-6 border-b border-white/10 pb-1 text-xl font-semibold" {...p} />,
          h3: (p) => <h3 className="mb-2 mt-4 text-lg font-semibold" {...p} />,
          ul: (p) => <ul className="my-2 list-disc space-y-1 pl-6" {...p} />,
          ol: (p) => <ol className="my-2 list-decimal space-y-1 pl-6" {...p} />,
          p: (p) => <p className="my-2" {...p} />,
          a: (p) => <a className="text-sky-400 underline underline-offset-2" target="_blank" rel="noreferrer" {...p} />,
          blockquote: (p) => <blockquote className="my-3 border-l-2 border-white/20 pl-4 opacity-80" {...p} />,
          code({ className, children }) {
            const code = String(children).replace(/\n$/, "");
            if (/language-mermaid/.test(className ?? "")) return <Mermaid code={code} />;
            if (!className && !code.includes("\n")) return <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[13px]">{code}</code>;
            return <code className={className}>{children}</code>;
          },
          pre: (p) => <pre className="my-3 overflow-x-auto rounded-xl border border-white/10 bg-black/40 p-4 font-mono text-[13px]" {...p} />,
          hr: () => <hr className="my-6 border-white/10" />,
          table: (p) => (
            <table className="my-3 w-full border-collapse text-sm [&_td]:border [&_td]:border-white/10 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-white/10 [&_th]:px-2 [&_th]:py-1" {...p} />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
