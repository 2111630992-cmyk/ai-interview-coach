import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { cn } from '../lib/utils'

/**
 * Markdown 渲染。
 * 不引入 @tailwindcss/typography，改为显式指定各元素的样式，
 * 这样报告里的长文本排版可控，也避免多一个构建依赖。
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn('text-sm leading-7', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children: c }) => <h1 className="mb-2 mt-4 text-lg font-semibold">{c}</h1>,
          h2: ({ children: c }) => <h2 className="mb-2 mt-4 text-base font-semibold">{c}</h2>,
          h3: ({ children: c }) => <h3 className="mb-1.5 mt-3 font-semibold">{c}</h3>,
          p: ({ children: c }) => <p className="my-2">{c}</p>,
          ul: ({ children: c }) => <ul className="my-2 list-disc space-y-1 pl-5">{c}</ul>,
          ol: ({ children: c }) => <ol className="my-2 list-decimal space-y-1 pl-5">{c}</ol>,
          li: ({ children: c }) => <li className="leading-7">{c}</li>,
          strong: ({ children: c }) => <strong className="font-semibold">{c}</strong>,
          em: ({ children: c }) => <em className="italic">{c}</em>,
          a: ({ children: c, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="text-primary underline underline-offset-4"
            >
              {c}
            </a>
          ),
          blockquote: ({ children: c }) => (
            <blockquote className="my-3 border-l-2 border-primary/40 pl-3 text-muted-foreground">
              {c}
            </blockquote>
          ),
          code: ({ children: c, className: cls }) => {
            const isBlock = Boolean(cls)
            return isBlock ? (
              <code className="block overflow-x-auto rounded-md bg-secondary p-3 font-mono text-xs">
                {c}
              </code>
            ) : (
              <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[0.85em]">{c}</code>
            )
          },
          pre: ({ children: c }) => <pre className="my-3">{c}</pre>,
          table: ({ children: c }) => (
            <div className="my-3 overflow-x-auto">
              <table className="w-full border-collapse text-xs">{c}</table>
            </div>
          ),
          th: ({ children: c }) => (
            <th className="border border-border bg-secondary/60 px-2 py-1 text-left font-medium">
              {c}
            </th>
          ),
          td: ({ children: c }) => <td className="border border-border px-2 py-1">{c}</td>,
          hr: () => <hr className="my-4 border-border" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
