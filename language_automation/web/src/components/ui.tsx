// Small building blocks that look like Streamlit's widgets (styles.css).
import { useEffect, useRef, type ReactNode } from "react";
import type { Kind } from "../types";

/** **bold** and `code` inside a sentence (the only markdown the page's texts use) */
export function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") && p.length > 4 ? (
          <strong key={i}>{p.slice(2, -2)}</strong>
        ) : p.startsWith("`") && p.endsWith("`") && p.length > 2 ? (
          <code key={i}>{p.slice(1, -1)}</code>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

export function Alert({ kind, children, pre }: { kind: Kind; children: ReactNode; pre?: boolean }) {
  return (
    <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {pre ? <div className="pre">{children}</div> : children}
    </div>
  );
}

export function Caption({ children }: { children: ReactNode }) {
  return <p className="caption">{children}</p>;
}

export function Toggle(props: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  help?: string;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className={`toggle${props.disabled ? " disabled" : ""}`} title={props.help}>
      <input
        type="checkbox"
        role="switch"
        checked={props.checked}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.checked)}
      />
      <span className="track" aria-hidden="true" />
      <span>{props.label}</span>
      {props.help && <span className="help" aria-label={props.help}>?</span>}
    </label>
  );
}

export function Expander(props: { title: ReactNode; defaultOpen?: boolean; children: ReactNode }) {
  return (
    <details className="box" open={props.defaultOpen}>
      <summary>
        <span>{props.title}</span>
        <span className="chev" aria-hidden="true">⌄</span>
      </summary>
      <div className="body">{props.children}</div>
    </details>
  );
}

/** Code block. fixed: 320 px high and kept scrolled to the bottom while lines arrive (st.container(height=320, autoscroll=True)). */
export function CodeLog({ lines, fixed }: { lines: string[]; fixed?: boolean }) {
  const ref = useRef<HTMLPreElement>(null);
  const count = lines.length;
  useEffect(() => {
    if (fixed && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [count, fixed]);
  return (
    <pre ref={ref} className={`code${fixed ? " fixed" : ""}`}>
      {lines.join("\n")}
    </pre>
  );
}

/** Saves text or a Blob as a file. No request to the server (spec 012, FR-001). */
export function saveFile(data: Blob | string, fileName: string, type = "text/plain;charset=utf-8") {
  const blob = typeof data === "string" ? new Blob([data], { type }) : data;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function DownloadButton(props: { label: string; onClick: () => void; primary?: boolean }) {
  return (
    <div>
      <button type="button" className={`btn${props.primary ? " primary" : ""}`} onClick={props.onClick}>
        {props.label}
      </button>
    </div>
  );
}
