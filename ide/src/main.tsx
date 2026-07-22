import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider, ClerkLoaded } from "@clerk/react";
import App from "./App.tsx";
import "./index.css";

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!publishableKey) {
  throw new Error(
    "Missing VITE_CLERK_PUBLISHABLE_KEY — add it to your .env file",
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClerkProvider publishableKey={publishableKey} afterSignOutUrl="/sign-in">
      <ClerkLoaded>
        <App />
      </ClerkLoaded>
    </ClerkProvider>
  </StrictMode>,
);
