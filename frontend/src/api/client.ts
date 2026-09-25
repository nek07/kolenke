import createFetchClient, { type Middleware } from "openapi-fetch";
import createClient from "openapi-react-query";

import type { components, paths } from "./schema";

/** Every state-changing request carries this header: the backend refuses requests that could come from other sites. */
const jobbotHeader: Middleware = {
  onRequest({ request }) {
    request.headers.set("X-JobBot", "1");
    return request;
  },
};

export const fetchClient = createFetchClient<paths>({ baseUrl: "" });
fetchClient.use(jobbotHeader);

/** Typed TanStack Query hooks for every endpoint: $api.useQuery("get", "/api/vacancies", ...). */
export const $api = createClient(fetchClient);

export type Schemas = components["schemas"];
export type Vacancy = Schemas["Vacancy"];
export type VacancyDetail = Schemas["VacancyDetail"];
export type VacancyStatus = Schemas["VacancyStatus"];
export type Stage = Schemas["Stage"];
export type Company = Schemas["Company"];
export type CompanyStatus = Schemas["CompanyStatus"];
export type ChatItem = Schemas["ChatItem"];
export type ChatStatus = Schemas["ChatStatus"];
export type Status = Schemas["Status"];
export type Settings = Schemas["SettingsOut"];
export type SettingsUpdate = Schemas["SettingsUpdate"];
export type Answer = Schemas["Answer-Output"];
export type TaskKey =
  | "hh_login"
  | "hh_check"
  | "hh_resumes"
  | "hh_search"
  | "hh_apply"
  | "hh_sync"
  | "hh_letters"
  | "hh_followups"
  | "other_search"
  | "chat_check"
  | "autopilot_now"
  | "mail_send";

type ValidationError = { loc: (string | number)[]; msg: string };

/** A readable message from any API error body: {detail: "..."} or FastAPI's 422 list. */
export function errorMessage(error: unknown): string {
  const detail = (error as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as ValidationError;
    const field = first.loc?.filter((p) => p !== "body").join(".");
    return field ? `${field}: ${first.msg}` : first.msg;
  }
  if (error instanceof Error) return error.message;
  return "Что-то пошло не так";
}

/** Field errors of a 422 response, keyed by field name, for forms. */
export function fieldErrors(error: unknown): Record<string, string> {
  const detail = (error as { detail?: unknown } | null)?.detail;
  if (!Array.isArray(detail)) return {};
  return Object.fromEntries((detail as ValidationError[]).map((d) => [String(d.loc[d.loc.length - 1]), d.msg]));
}
