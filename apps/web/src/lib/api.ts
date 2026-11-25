import { createApiClient, type ApiProblem, type Schemas } from "@personal-os/api-client";

export type { Schemas };

/** Typed client for the Personal OS API (same origin; cookies are sent automatically). */
export const api = createApiClient("");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem?: Partial<ApiProblem>;

  constructor(status: number, code: string, message: string, problem?: Partial<ApiProblem>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.problem = problem;
  }
}

type FetchResult<D> = { data?: D; error?: unknown; response: Response };

/** Returns the response data, or throws an ApiError built from the RFC 9457 problem body. */
export async function unwrap<D>(request: Promise<FetchResult<D>>): Promise<D> {
  const { data, error, response } = await request;
  if (!response.ok) {
    const problem = (typeof error === "object" && error !== null ? error : {}) as Partial<ApiProblem>;
    if (response.status === 401 && typeof window !== "undefined") {
      const here = window.location.pathname;
      if (!here.startsWith("/login")) {
        // Outside React (no router here); a full reload also drops cached personal data.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign(`/login?next=${encodeURIComponent(here)}`);
      }
    }
    throw new ApiError(
      response.status,
      problem.code ?? "http_error",
      problem.detail ?? problem.title ?? `Request failed (${response.status})`,
      problem,
    );
  }
  return data as D;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
