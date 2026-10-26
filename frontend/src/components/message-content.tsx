"use client";

import rehypeHighlight from "rehype-highlight";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MessageContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      rehypePlugins={[rehypeHighlight]}
      remarkPlugins={[remarkGfm]}
    >
      {content}
    </ReactMarkdown>
  );
}
