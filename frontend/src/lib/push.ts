import { api, post } from "./api";

export type PushState = "unsupported" | "denied" | "off" | "on";

export const SUBSCRIBE_TIMEOUT_MS = 30_000;

export function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), ms);
    promise.then(
      (value) => (clearTimeout(timer), resolve(value)),
      (error) => (clearTimeout(timer), reject(error)),
    );
  });
}

export function pushSupported() {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function keyBytes(base64url: string) {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export function deviceLabel(agent = navigator.userAgent) {
  const os = /Android/i.test(agent) ? "Android" : /iPhone|iPad/i.test(agent) ? "iPhone or iPad" : /Windows/i.test(agent) ? "Windows" : /Mac OS/i.test(agent) ? "Mac" : /Linux/i.test(agent) ? "Linux" : "Device";
  const browser = /Edg\//.test(agent) ? "Edge" : /Firefox\//.test(agent) ? "Firefox" : /Chrome\//.test(agent) ? "Chrome" : /Safari\//.test(agent) ? "Safari" : "browser";
  const installed = window.matchMedia?.("(display-mode: standalone)").matches ? " (installed app)" : "";
  return `${os} · ${browser}${installed}`;
}

async function registration() {
  const existing = await navigator.serviceWorker.getRegistration();
  if (existing) return navigator.serviceWorker.ready;
  // Development builds do not register the worker on load; push needs it.
  await navigator.serviceWorker.register("/sw.js");
  return navigator.serviceWorker.ready;
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  return sub && Notification.permission === "granted" ? "on" : "off";
}

/** Ask permission, subscribe this device and register it with the server. */
export async function enablePush(publicKey: string) {
  if (!pushSupported()) throw new Error("This browser cannot receive notifications.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications are blocked. Allow them for CharityOS in your browser or phone settings.");
  const reg = await registration();
  let sub = await reg.pushManager.getSubscription();
  // The browser registers with its push service (Google's, on Android) the
  // first time; that can stall on a poor connection. Never wait silently.
  if (!sub)
    sub = await withTimeout(
      reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) }),
      SUBSCRIBE_TIMEOUT_MS,
      "Your browser's push service did not answer in time. Check your connection and tap Turn on notifications again.",
    );
  const json = sub.toJSON();
  await post("/push/subscriptions", { endpoint: json.endpoint, keys: json.keys, device_label: deviceLabel() });
}

export async function disablePush() {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  if (!sub) return;
  await post("/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => undefined);
  await sub.unsubscribe();
}

export type PushConfig = { configured: boolean; public_key: string | null };
export const loadPushConfig = () => api<PushConfig>("/push/config");
