import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { PersonalWishesState } from "./api";
import { Navbar } from "./components/Navbar";
import { ChatPanel } from "./components/ChatPanel";
import type { ChatMessage } from "./components/ChatPanel";
import { StatePanel } from "./components/StatePanel";
import { DocumentPanel } from "./components/DocumentPanel";
import "./index.css";

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [state, setState] = useState<PersonalWishesState>({
    full_name: null,
    home_address: null,
    covers_worldwide_assets: null,
    has_children: null,
    children_names: [],
    executor: null,
    specific_gifts: [],
    additional_wishes: null,
  });
  const [document, setDocument] = useState("");
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // On mount: reset to get the initial greeting, state, document, and missing fields
  // in a single request — no need for a separate GET /api/state
  useEffect(() => {
    api.reset().then((res) => {
      setMessages([{ role: "assistant", content: res.reply }]);
      setState(res.state);
      setDocument(res.document);
      setMissingFields(res.missing_fields);
    });
  }, []);

  const handleSend = useCallback(async (message: string) => {
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setIsLoading(true);

    try {
      const res = await api.chat(message);
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
      setState(res.state);
      setDocument(res.document);
      setMissingFields(res.missing_fields);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Something went wrong: ${msg}` },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleReset = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.reset();
      setMessages([{ role: "assistant", content: res.reply }]);
      setState(res.state);
      setDocument(res.document);
      setMissingFields(res.missing_fields);
      setError(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleEdit = useCallback(async (field: string, value: unknown) => {
    try {
      const res = await api.manualEdit(field, value);
      setState(res.state);
      setDocument(res.document);
      setMissingFields(res.missing_fields);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Edit failed";
      setError(msg);
    }
  }, []);

  return (
    <div className="app">
      <Navbar onReset={handleReset} isLoading={isLoading} />

      {error && (
        <div style={{ margin: "0 1.5rem 1rem", padding: "0.75rem 1rem", background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", borderRadius: "8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>{error}</span>
          <button onClick={() => setError(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "#b91c1c", fontWeight: "bold", fontSize: "1rem" }}>✕</button>
        </div>
      )}

      <div className="main-grid">
        <ChatPanel
          messages={messages}
          isLoading={isLoading}
          onSend={handleSend}
        />

        <StatePanel
          state={state}
          missingFields={missingFields}
          onEdit={handleEdit}
        />

        {/* Document preview spans full bottom-right area */}
        <DocumentPanel document={document} />
      </div>
    </div>
  );
}
