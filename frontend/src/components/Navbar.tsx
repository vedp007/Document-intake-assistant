interface Props {
  onReset: () => void;
  isLoading: boolean;
}

export function Navbar({ onReset, isLoading }: Props) {
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <div className="navbar-logo">W</div>
        <div>
          <div className="navbar-name">Document Intake Assistant</div>
          <div className="navbar-subtitle">Personal Wishes Document Capture</div>
        </div>
      </div>

      <div className="navbar-right">
        <span className="provider-badge">Mock LLM</span>
        <button
          id="btn-reset"
          className="btn btn-danger"
          onClick={onReset}
          disabled={isLoading}
          title="Start a new session"
        >
          ↺ Reset
        </button>
      </div>
    </nav>
  );
}
