import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };

/** All API schema types, e.g. `Schemas["TaskOut"]`. */
export type Schemas = components["schemas"];

/**
 * Creates a typed client for the Personal OS API.
 *
 * The web app calls the API on its own origin (`/api/v1/...` is proxied to FastAPI),
 * so cookies stay first-party and no CORS is needed.
 */
export function createApiClient(baseUrl = "") {
  return createClient<paths>({ baseUrl, credentials: "same-origin" });
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** Shape of an RFC 9457 problem response returned by the API on errors. */
export interface ApiProblem {
  type: string;
  title: string;
  status: number;
  detail?: string | null;
  code: string;
  instance?: string;
  errors?: Array<{ loc: Array<string | number>; msg: string; type: string }>;
  [key: string]: unknown;
}
