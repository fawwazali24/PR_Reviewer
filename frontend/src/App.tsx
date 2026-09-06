import { Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Review from "./pages/Review";

export default function App() {
  return (
    <>
      <header className="app-header">
        <Link to="/" style={{ color: "var(--text)" }}>
          <h1>AI&nbsp;PR&nbsp;Reviewer</h1>
        </Link>
        <span className="badge">read-only</span>
        <div className="spacer" />
        <span className="faint small">
          
        </span>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/reviews/:reviewId" element={<Review />} />
      </Routes>
    </>
  );
}
