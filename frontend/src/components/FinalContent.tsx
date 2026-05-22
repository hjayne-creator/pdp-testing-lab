import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function looksLikeHtml(content: string): boolean {
  return /<\/?[a-z][\s\S]*>/i.test(content);
}

/** Some model responses stringify newlines as literal `\n`. */
function normalizeNewlines(content: string): string {
  if (!content.includes("\n") && content.includes("\\n")) {
    return content.replace(/\\n/g, "\n");
  }
  return content;
}

type FinalContentProps = {
  content: string;
};

export function FinalContent({ content }: FinalContentProps) {
  const normalized = normalizeNewlines(content);

  if (looksLikeHtml(normalized)) {
    return (
      <div
        className="output-box markdown-content"
        dangerouslySetInnerHTML={{ __html: normalized }}
      />
    );
  }

  return (
    <div className="output-box markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{normalized}</ReactMarkdown>
    </div>
  );
}
