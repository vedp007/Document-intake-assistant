import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, Ref } from "react";

interface Props {
  field: string;
  label: string;
  currentValue: string;
  onSave: (field: string, value: unknown) => void;
  onClose: () => void;
}

const BOOLEAN_FIELDS = new Set(["covers_worldwide_assets", "has_children"]);

export function EditFieldModal({ field, label, currentValue, onSave, onClose }: Props) {
  const [value, setValue] = useState(currentValue);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement | HTMLSelectElement>(null);

  useEffect(() => {
    (inputRef.current as HTMLElement | null)?.focus();
  }, []);

  const handleSave = () => {
    if (!value && !BOOLEAN_FIELDS.has(field)) {
      setError("Value cannot be empty.");
      return;
    }

    let finalValue: unknown = value;

    if (BOOLEAN_FIELDS.has(field)) {
      finalValue = value === "true";
    }

    onSave(field, finalValue);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter") handleSave();
    if (e.key === "Escape") onClose();
  };

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-title" id="modal-title">Edit {label}</div>
        <div className="modal-subtitle">
          Update this field directly. The document will refresh immediately.
        </div>

        {error && <div className="modal-error">{error}</div>}

        {BOOLEAN_FIELDS.has(field) ? (
          <select
            ref={inputRef as Ref<HTMLSelectElement>}
            id={`modal-input-${field}`}
            className="modal-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
          >
            <option value="">— Select —</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        ) : (
          <input
            ref={inputRef as Ref<HTMLInputElement>}
            id={`modal-input-${field}`}
            className="modal-input"
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Enter ${label.toLowerCase()}…`}
          />
        )}

        <div className="modal-actions">
          <button
            id="modal-cancel"
            className="btn btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            id="modal-save"
            className="btn btn-primary"
            onClick={handleSave}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
