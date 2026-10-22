import { createRoot } from "react-dom/client";
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { MotherDuckSDKProvider, useConnectionStatus } from "./md-sdk-runtime";
import { Loader2, AlertCircle } from "lucide-react";
import Dive, { REQUIRED_DATABASES } from "./dive";

function ConnectionGate({ children }: { children: ReactNode }) {
  const { isConnected, isConnecting, error } = useConnectionStatus();
  if (isConnecting) return (
    <div className="flex items-center justify-center h-screen gap-2 text-[#6a6a6a]">
      <Loader2 className="animate-spin" size={20} />
      Connecting to MotherDuck…
    </div>
  );
  if (error) return (
    <div className="flex flex-col items-center justify-center h-screen gap-2 px-8 text-center text-red-600">
      <div className="flex items-center gap-2">
        <AlertCircle size={20} />
        Connection failed: {error.message}
      </div>
      <p className="text-sm text-[#6a6a6a]">
        If the token was rejected, set VITE_MOTHERDUCK_TOKEN in .dive-preview/.env to a read/write token
        from app.motherduck.com, Settings, API Tokens, then restart make preview.
      </p>
    </div>
  );
  if (!isConnected) return null;
  return <>{children}</>;
}

// Without a boundary, an error thrown while rendering the Dive leaves a blank page.
class DiveErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("The Dive failed to render:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="p-8 text-red-600">
        <p className="flex items-center gap-2 font-medium">
          <AlertCircle size={20} />
          The Dive failed to render: {this.state.error.message}
        </p>
        <p className="mt-2 text-sm text-[#6a6a6a]">
          Fix the error in the Dive source. The browser console has the component stack. The page reloads on save.
        </p>
      </div>
    );
  }
}

const token = import.meta.env.VITE_MOTHERDUCK_TOKEN?.trim();
if (!token || token === "your_token_here") {
  document.getElementById("root")!.innerHTML =
    '<p style="padding:2rem;color:red">Set VITE_MOTHERDUCK_TOKEN in .dive-preview/.env to a read/write token ' +
    "from app.motherduck.com (Settings, API Tokens), then restart make preview. make setup creates the file " +
    "from .env.example. make preview-smoke needs no token.</p>";
} else {
  // The local developer previews as the Dive's owner, who may run Flights in production.
  createRoot(document.getElementById("root")!).render(
    <MotherDuckSDKProvider token={token} requiredDatabases={REQUIRED_DATABASES} allowedFlights="any">
      <ConnectionGate>
        <DiveErrorBoundary>
          <Dive />
        </DiveErrorBoundary>
      </ConnectionGate>
    </MotherDuckSDKProvider>
  );
}
