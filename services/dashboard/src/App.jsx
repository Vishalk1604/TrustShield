import React from "react";
import { Routes, Route } from "react-router-dom";
import Shell from "./components/Shell.jsx";
import Home from "./pages/Home.jsx";
import Investigator from "./pages/Investigator.jsx";
import Examples from "./pages/Examples.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route path="investigator" element={<Investigator />} />
        <Route path="examples" element={<Examples />} />
      </Route>
    </Routes>
  );
}
