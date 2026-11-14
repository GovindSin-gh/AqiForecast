import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import App from "./App.jsx";
import "./styles.css";

class Boundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? <main><h1>Something went wrong</h1><p>Please reload the page.</p></main>
      : this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Boundary><BrowserRouter><App /></BrowserRouter></Boundary>
  </React.StrictMode>
);
