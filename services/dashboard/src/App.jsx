import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Nav from "./components/Nav.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Home from "./pages/Home.jsx";
import About from "./pages/About.jsx";
import SignIn from "./pages/SignIn.jsx";
import SignUp from "./pages/SignUp.jsx";
import UserDashboard from "./pages/UserDashboard.jsx";
import AdminDashboard from "./pages/AdminDashboard.jsx";
import CaseDetail from "./pages/CaseDetail.jsx";

export default function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/about" element={<About />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="/app" element={<ProtectedRoute><UserDashboard /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute admin><AdminDashboard /></ProtectedRoute>} />
        <Route path="/case/:id" element={<ProtectedRoute><CaseDetail /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <footer style={{ marginTop: 36, fontSize: 12, color: "#475569", borderTop: "1px solid #1e293b", padding: "12px 24px", textAlign: "center" }}>
        TrustShield — 100% local, zero PII leaves the machine. Every score carries a full evidence chain.
      </footer>
    </>
  );
}
