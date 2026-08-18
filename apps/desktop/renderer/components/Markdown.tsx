import React from "react";
import { Prose } from "../ui";

/** Minimal markdown → React nodes (headings, bold, lists, paragraphs, code). */
export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];

  const flushList = () => {
    if (!list.length) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {list.map((item, i) => (
          <li key={i}>{inlineMd(item)}</li>
        ))}
      </ul>
    );
    list = [];
  };

  const inlineMd = (s: string): React.ReactNode => {
    const parts: React.ReactNode[] = [];
    const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let k = 0;
    while ((m = re.exec(s))) {
      if (m.index > last) parts.push(s.slice(last, m.index));
      const tok = m[0];
      if (tok.startsWith("**")) {
        parts.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
      } else {
        parts.push(<code key={k++}>{tok.slice(1, -1)}</code>);
      }
      last = m.index + tok.length;
    }
    if (last < s.length) parts.push(s.slice(last));
    return parts.length === 1 ? parts[0] : <>{parts}</>;
  };

  for (const line of lines) {
    if (/^\s*[-*]\s+/.test(line)) {
      list.push(line.replace(/^\s*[-*]\s+/, ""));
      continue;
    }
    flushList();
    if (/^###\s+/.test(line)) {
      blocks.push(
        <h4 key={`h-${blocks.length}`}>{inlineMd(line.replace(/^###\s+/, ""))}</h4>
      );
    } else if (/^##\s+/.test(line)) {
      blocks.push(
        <h3 key={`h-${blocks.length}`}>{inlineMd(line.replace(/^##\s+/, ""))}</h3>
      );
    } else if (/^#\s+/.test(line)) {
      blocks.push(
        <h2 key={`h-${blocks.length}`}>{inlineMd(line.replace(/^#\s+/, ""))}</h2>
      );
    } else if (line.trim() === "") {
      blocks.push(<div key={`sp-${blocks.length}`} className="md-sp" />);
    } else {
      blocks.push(<p key={`p-${blocks.length}`}>{inlineMd(line)}</p>);
    }
  }
  flushList();
  return (
    <Prose>
      <div className="md-body">{blocks}</div>
    </Prose>
  );
}

export default Markdown;
