import { useEffect, useRef, useState, useCallback } from "react";
import { wsBaseUrl } from "../lib/runtime-config";

const WS_BASE = wsBaseUrl();

export function useAgentWebSocket(jobId) {
  const ws = useRef(null);
  const [logs, setLogs] = useState([]);
  const [screenshot, setScreenshot] = useState(null);
  // History of every screenshot the agent captured: { url, caption }.
  const [screenshots, setScreenshots] = useState([]);
  const [requireOtp, setRequireOtp] = useState(false);
  const [connected, setConnected] = useState(false);
  // Map of step name → { state, message } for the prep/submit progress tracker.
  const [steps, setSteps] = useState({});

  useEffect(() => {
    if (!jobId) return;
    setSteps({});       // reset progress when switching applications
    setScreenshots([]);
    setScreenshot(null);
    setLogs([]);

    let closedByUnmount = false;
    let reconnectTimer = null;
    let attempts = 0;

    const handleMessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        // Ignore malformed/binary frames instead of letting the throw kill the handler.
        return;
      }
      switch (msg.type) {
        case "log":
          setLogs((prev) => [...prev, msg.message]);
          break;
        case "screenshot": {
          const url = `data:image/jpeg;base64,${msg.data}`;
          setScreenshot(url);
          setScreenshots((prev) => {
            const next = [...prev, { url, caption: msg.caption || "" }];
            return next.length > 20 ? next.slice(next.length - 20) : next;
          });
          break;
        }
        case "require_otp":
          setRequireOtp(true);
          break;
        case "step":
          setSteps((prev) => ({
            ...prev,
            [msg.step]: { state: msg.state, message: msg.message },
          }));
          break;
        default:
          break;
      }
    };

    const connect = () => {
      const token = localStorage.getItem("token");
      const socket = new WebSocket(
        `${WS_BASE}/agent/${jobId}?token=${encodeURIComponent(token || "")}`
      );
      ws.current = socket;

      socket.onopen = () => {
        attempts = 0;
        setConnected(true);
      };
      socket.onmessage = handleMessage;
      socket.onclose = () => {
        setConnected(false);
        if (closedByUnmount) return;
        // Reconnect with capped exponential backoff (1s → 10s) so a dropped
        // socket recovers instead of leaving the console stuck "Disconnected".
        attempts += 1;
        const delay = Math.min(1000 * 2 ** (attempts - 1), 10_000);
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      closedByUnmount = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws.current) ws.current.close();
    };
  }, [jobId]);

  const resetOtp = useCallback(() => setRequireOtp(false), []);

  return { logs, screenshot, screenshots, requireOtp, connected, resetOtp, steps };
}
