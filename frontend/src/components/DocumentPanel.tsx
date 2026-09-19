import { useRef } from "react";

interface Props {
  document: string;
}

export function DocumentPanel({ document }: Props) {
  const preRef = useRef<HTMLPreElement>(null);

  // Highlight disclaimer lines in the rendered text
  const renderDoc = (text: string) => {
    return text.split("\n").map((line, i) => {
      const isDisclaimer =
        line.includes("FICTIONAL") || line.includes("NOT LEGAL ADVICE");
      return (
        <span
          key={i}
          style={isDisclaimer ? { color: "#f87171", fontWeight: 700 } : undefined}
        >
          {line}
          {"\n"}
        </span>
      );
    });
  };

  return (
    <div className="panel doc-panel">
      <div className="panel-header">
        <span className="panel-title">📄 Document Preview</span>
      </div>

      <div className="panel-body">
        <pre
          ref={preRef}
          className="doc-pre"
          id="document-preview"
          aria-label="Personal Wishes Document Preview"
        >
          {renderDoc(document)}
        </pre>
      </div>
    </div>
  );
}
