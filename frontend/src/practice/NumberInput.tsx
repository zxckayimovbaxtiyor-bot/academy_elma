import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type InputHTMLAttributes,
} from "react";
import { editNumber, numberText } from "../lib/numberInput";
import type { Value } from "../api/practice";

export function NumberInput({
  value,
  change,
  ...props
}: Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange" | "type"
> & {
  value: Value;
  change: (value: Value) => void;
}) {
  const [text, setText] = useState(() => numberText(value));
  const element = useRef<HTMLInputElement>(null);
  const caret = useRef<number | null>(null);
  useEffect(() => {
    setText((current) =>
      editNumber("", current, 0)?.value === value ? current : numberText(value),
    );
  }, [value]);
  useLayoutEffect(() => {
    if (caret.current !== null) {
      element.current?.setSelectionRange(caret.current, caret.current);
      caret.current = null;
    }
  });
  return (
    <input
      {...props}
      ref={element}
      type="text"
      inputMode="decimal"
      value={text}
      maxLength={2000}
      onChange={(event) => {
        const target = event.currentTarget;
        const edited = editNumber(
          text,
          target.value,
          target.selectionStart ?? target.value.length,
          (event.nativeEvent as InputEvent).inputType,
        );
        if (!edited) return;
        caret.current = edited.caret;
        setText(edited.text);
        change(edited.value);
      }}
    />
  );
}
