import type { ProblemDocument } from "@/types/api";

type FetchLike = typeof fetch;

export interface ApiClientOptions {
  baseUrl: string;
  getToken: () => string | null;
  onUnauthorized?: () => void;
  fetchImpl?: FetchLike;
}

export interface ApiRequestOptions {
  signal?: AbortSignal;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly detail: string;
  readonly problem: ProblemDocument | null;

  constructor(message: string, options: {
    status: number;
    code: string;
    requestId?: string | null;
    detail?: string;
    problem?: ProblemDocument | null;
  }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId ?? null;
    this.detail = options.detail ?? message;
    this.problem = options.problem ?? null;
  }
}

export function createApiClient(options: ApiClientOptions) {
  const fetchImpl = options.fetchImpl ?? fetch;

  async function request<T>(
    method: string,
    path: string,
    body?: unknown,
    requestOptions: ApiRequestOptions = {},
  ): Promise<T> {
    const response = await fetchImpl(buildUrl(options.baseUrl, path), {
      method,
      signal: requestOptions.signal,
      headers: buildHeaders(options.getToken(), body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await responseToApiError(response);
      if (error.status === 401) {
        options.onUnauthorized?.();
      }
      throw error;
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  return {
    get<T>(path: string, options?: ApiRequestOptions) {
      return request<T>("GET", path, undefined, options);
    },
    post<T>(path: string, body: unknown, options?: ApiRequestOptions) {
      return request<T>("POST", path, body, options);
    },
    delete<T>(path: string, options?: ApiRequestOptions) {
      return request<T>("DELETE", path, undefined, options);
    },
  };
}

export function buildUrl(baseUrl: string, path: string): string {
  if (!baseUrl) {
    return path;
  }
  return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

export async function responseToApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("x-request-id");
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/problem+json") || contentType.includes("application/json")) {
    const problem = (await response.json()) as ProblemDocument;
    return new ApiError(problem.detail ?? problem.title ?? "Request failed", {
      status: response.status,
      code: problem.code ?? `http_${response.status}`,
      requestId: problem.request_id ?? requestId,
      detail: problem.detail,
      problem,
    });
  }

  return new ApiError(response.statusText || "Request failed", {
    status: response.status,
    code: `http_${response.status}`,
    requestId,
  });
}

function buildHeaders(token: string | null, hasBody: boolean): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (hasBody) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}
