import confetti from "canvas-confetti";
import { toast } from "sonner";

const COLORS = ["#FFD43B", "#141414", "#1F9D62", "#2F6FEB", "#E0463C", "#FFFFFF"];

/** Confetti and a warm toast: for invitations, offers and reached goals. */
export function celebrate(message: string) {
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    void confetti({ particleCount: 140, spread: 80, origin: { y: 0.35 }, colors: COLORS, disableForReducedMotion: true });
  }
  toast.success(message, { duration: 5000 });
}

/** Per-browser memory for «already celebrated» marks. Storage may be blocked: then nothing is remembered. */
export const memory = {
  get<T>(key: string, fallback: T): T {
    try {
      const v = localStorage.getItem(`kolenke.${key}`);
      return v === null ? fallback : (JSON.parse(v) as T);
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown) {
    try {
      localStorage.setItem(`kolenke.${key}`, JSON.stringify(value));
    } catch {
      /* private mode */
    }
  },
};
