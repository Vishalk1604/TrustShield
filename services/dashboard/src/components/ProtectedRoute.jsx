// Route guards: redirect to /signin when unauthenticated; bounce non-admins off admin routes.
import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function ProtectedRoute({ children, admin = false }) {
  const { auth } = useAuth();
  if (!auth) return <Navigate to="/signin" replace />;
  if (admin && auth.role !== "admin") return <Navigate to="/app" replace />;
  return children;
}
