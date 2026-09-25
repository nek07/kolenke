import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig, devices } from "@playwright/test";

// A throwaway backend with seeded data on its own ports: your real kolenke and its data stay untouched.
const API_PORT = 8781;
const WEB_PORT = 3181;
const DATA_DIR = process.env.KOLENKE_E2E_DATA ?? mkdtempSync(join(tmpdir(), "kolenke-e2e-"));

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the tests share one database
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /smoke/ },
  ],
  webServer: [
    {
      command: `../.venv/bin/python tests/e2e_seed.py && ../.venv/bin/uvicorn kolenke.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: "../backend",
      env: { KOLENKE_DATA_DIR: DATA_DIR, KOLENKE_BACKGROUND: "false" },
      url: `http://127.0.0.1:${API_PORT}/openapi.json`,
      reuseExistingServer: false,
    },
    {
      command: `npx next build && npx next start --port ${WEB_PORT} --hostname 127.0.0.1`,
      env: { KOLENKE_API_URL: `http://127.0.0.1:${API_PORT}`, KOLENKE_DIST_DIR: ".next-e2e" },
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
