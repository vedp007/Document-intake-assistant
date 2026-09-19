import { useState } from "react";
import type { PersonalWishesState } from "../api";
import { EditFieldModal } from "./EditFieldModal";

interface FieldDef {
  key: keyof PersonalWishesState;
  label: string;
  format: (state: PersonalWishesState) => string | null;
  editType: "text" | "boolean" | "none";
  editKey?: string;        // backend field key (may differ)
  editLabel?: string;
}

const FIELDS: FieldDef[] = [
  {
    key: "full_name",
    label: "Full Name",
    format: (s) => s.full_name,
    editType: "text",
  },
  {
    key: "home_address",
    label: "Home Address",
    format: (s) => s.home_address,
    editType: "text",
  },
  {
    key: "covers_worldwide_assets",
    label: "Worldwide Assets",
    format: (s) =>
      s.covers_worldwide_assets === true
        ? "Yes — worldwide"
        : s.covers_worldwide_assets === false
        ? "No — not worldwide"
        : null,
    editType: "boolean",
  },
  {
    key: "has_children",
    label: "Has Children",
    format: (s) =>
      s.has_children === true
        ? `Yes${s.children_names.length ? ` (${s.children_names.join(", ")})` : ""}`
        : s.has_children === false
        ? "No"
        : null,
    editType: "boolean",
  },
  {
    key: "executor",
    label: "Executor",
    format: (s) => {
      if (!s.executor) return null;
      const parts: string[] = [];
      if (s.executor.name) parts.push(s.executor.name);
      if (s.executor.relationship) parts.push(`(${s.executor.relationship})`);
      return parts.join(" ") || null;
    },
    editType: "none",   // complex nested — edit via chat
  },
  {
    key: "specific_gifts",
    label: "Specific Gifts",
    format: (s) => {
      if (s.specific_gifts === null) return null;
      if (s.specific_gifts.length === 0) return "None specified.";
      return s.specific_gifts.map((g) => `${g.description} \u2192 ${g.recipient}`).join("\n");
    },
    editType: "none",
  },
  {
    key: "additional_wishes",
    label: "Additional Wishes",
    format: (s) => s.additional_wishes,
    editType: "text",
  },
];

interface Props {
  state: PersonalWishesState;
  missingFields: string[];
  onEdit: (field: string, value: unknown) => void;
}

export function StatePanel({ state, missingFields, onEdit }: Props) {
  const [editing, setEditing] = useState<{ field: string; label: string; currentValue: string } | null>(null);

  const totalFields = FIELDS.length;
  const filledFields = FIELDS.filter((f) => {
    const v = state[f.key];
    if (f.key === "specific_gifts") {
      // null  = not yet answered   → unfilled
      // []    = confirmed no gifts → filled
      // [...] = has gifts          → filled
      return v !== null && v !== undefined;
    }
    if (f.key === "has_children") return v !== null && v !== undefined;
    if (f.key === "covers_worldwide_assets") return v !== null && v !== undefined;
    return !!v;
  }).length;

  const pct = Math.round((filledFields / totalFields) * 100);

  return (
    <div className="panel state-panel">
      <div className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="panel-title">📋 Information Captured</span>
        {missingFields.length > 0 ? (
          <span style={{ fontSize: "0.75rem", padding: "2px 8px", borderRadius: "10px", background: "rgba(245, 158, 11, 0.15)", color: "#f59e0b" }}>
            {missingFields.length} pending
          </span>
        ) : (
          <span style={{ fontSize: "0.75rem", padding: "2px 8px", borderRadius: "10px", background: "rgba(16, 185, 129, 0.15)", color: "#10b981" }}>
            Complete
          </span>
        )}
      </div>

      <div className="panel-body">
        {/* Progress bar */}
        <div className="progress-bar-wrap">
          <div className="progress-label">
            <span>Completion</span>
            <span id="completion-pct">{pct}%</span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>

        <div className="field-list">
          {FIELDS.map((fieldDef) => {
            const formatted = fieldDef.format(state);
            const isFilled = formatted !== null && formatted !== "";

            return (
              <div
                key={fieldDef.key}
                className={`field-card ${isFilled ? "filled" : ""}`}
                id={`field-${fieldDef.key}`}
              >
                <div className={`field-status-dot ${isFilled ? "filled" : "empty"}`} />

                <div className="field-content">
                  <div className="field-label">{fieldDef.label}</div>
                  <div className={`field-value ${isFilled ? "" : "empty"}`}>
                    {isFilled ? formatted : "Not yet provided"}
                  </div>
                </div>

                {fieldDef.editType !== "none" && (
                  <button
                    id={`edit-${fieldDef.key}`}
                    className="btn btn-icon field-edit-btn"
                    title={`Edit ${fieldDef.label}`}
                    onClick={() =>
                      setEditing({
                        field: fieldDef.key as string,
                        label: fieldDef.label,
                        currentValue: formatted ?? "",
                      })
                    }
                  >
                    ✎
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {editing && (
        <EditFieldModal
          field={editing.field}
          label={editing.label}
          currentValue={editing.currentValue}
          onSave={(field, value) => {
            onEdit(field, value);
            setEditing(null);
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
