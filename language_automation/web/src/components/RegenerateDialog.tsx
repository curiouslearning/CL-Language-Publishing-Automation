// "Language already generated" (spec 004): Yes regenerates; No or closing runs only the new languages.
import { useEffect } from "react";
import { Caption, Inline } from "./ui";

export function RegenerateDialog(props: { existing: Record<string, number>; hosted: boolean; onAnswer: (regenerate: boolean) => void }) {
  const { onAnswer } = props;
  const names = Object.keys(props.existing);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onAnswer(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onAnswer]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onAnswer(false)}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="regen-title">
        <button type="button" className="close" aria-label="Close" onClick={() => onAnswer(false)}>
          ✕
        </button>
        <h3 id="regen-title">Language already generated</h3>
        {names.map((lang) => (
          <p key={lang} className="md">
            <Inline
              text={
                props.hosted
                  ? `**${lang}** was already generated on this page, with **${props.existing[lang]}** audio file(s).`
                  : `**${lang}** already has its game JSON and **${props.existing[lang]}** audio file(s) in \`lang/${lang.toLowerCase()}/\`.`
              }
            />
          </p>
        ))}
        <p>{names.length === 1 ? "Do you need to regenerate this language?" : "Do you need to regenerate these languages?"}</p>
        <Caption>Regenerating deletes the current folder and downloads everything again from Google Drive.</Caption>
        <div className="cols2">
          <button type="button" className="btn primary stretch" autoFocus onClick={() => onAnswer(true)}>
            Yes, regenerate
          </button>
          <button type="button" className="btn stretch" onClick={() => onAnswer(false)}>
            No
          </button>
        </div>
      </div>
    </div>
  );
}
