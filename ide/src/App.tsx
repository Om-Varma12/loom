import { BrowserRouter, Routes, Route } from "react-router";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { PublicOnlyRoute } from "./routes/PublicOnlyRoute";
import SignIn from "./pages/SignIn";
import SignUp from "./pages/SignUp";
import SsoCallback from "./pages/SsoCallback";
import Home from "./pages/Home";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<PublicOnlyRoute />}>
          <Route path="/sign-in" element={<SignIn />} />
          <Route path="/sign-up" element={<SignUp />} />
        </Route>

        {/* The OAuth redirect lands here regardless of auth state, so it's outside both guards */}
        <Route path="/sso-callback" element={<SsoCallback />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<Home />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
