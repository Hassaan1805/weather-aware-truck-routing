import { useEffect, useId, useRef, useState } from "react";
import { searchPlaces } from "../api";
import type { Place } from "../types";

interface Props {
  label: string;
  value: Place;
  onChange: (place: Place) => void;
  placeholder?: string;
}

/** Text field with place autocomplete. Free text is allowed; the server geocodes it. */
export default function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId();
  const [results, setResults] = useState<Required<Place>[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const typed = useRef(false);

  useEffect(() => {
    // Only search when the user typed, not when a suggestion was picked.
    if (!typed.current || value.label.trim().length < 2) {
      setResults([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      searchPlaces(value.label, ctrl.signal)
        .then((r) => {
          setResults(r.results);
          setActive(-1);
          setOpen(true);
        })
        .catch(() => setResults([]));
    }, 250);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [value.label]);

  const pick = (p: Required<Place>) => {
    typed.current = false;
    onChange(p);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? results.length - 1 : a - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="field place-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={`${id}-list`}
        placeholder={placeholder}
        value={value.label}
        required
        onChange={(e) => {
          typed.current = true;
          onChange({ label: e.target.value });
        }}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {value.lat !== undefined && <span className="place-ok" title="Location found" aria-label="Location found" />}
      {open && results.length > 0 && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {results.map((r, i) => (
            <li
              key={`${r.lat},${r.lon},${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(r);
              }}
            >
              {r.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
