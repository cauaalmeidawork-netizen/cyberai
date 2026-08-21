import { NextResponse } from "next/server";

export const runtime = "nodejs";

const API_PROXY_TARGET =
  process.env.API_PROXY_TARGET ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

type CookieOptions = {
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: "lax" | "strict" | "none";
  path?: string;
  maxAge?: number;
};

function readSetCookies(headers: Headers): string[] {
  const withGetSetCookie = headers as Headers & { getSetCookie?: () => string[] };
  const cookies = withGetSetCookie.getSetCookie?.() ?? [];
  if (cookies.length > 0) return cookies;

  const combined = headers.get("set-cookie");
  if (!combined) return [];
  return combined.split(/,(?=\s*[^;,]+=)/g).map((value) => value.trim());
}

function parseCookie(raw: string): { name: string; value: string; options: CookieOptions } | null {
  const parts = raw.split(";").map((part) => part.trim());
  const first = parts.shift();
  if (!first) return null;

  const equalsIndex = first.indexOf("=");
  if (equalsIndex <= 0) return null;

  const name = first.slice(0, equalsIndex);
  const value = first.slice(equalsIndex + 1);
  const options: CookieOptions = { path: "/" };

  for (const part of parts) {
    const [rawKey, ...rawValueParts] = part.split("=");
    const key = rawKey.toLowerCase();
    const attrValue = rawValueParts.join("=");

    if (key === "httponly") options.httpOnly = true;
    else if (key === "secure") options.secure = true;
    else if (key === "path" && attrValue) options.path = attrValue;
    else if (key === "max-age" && attrValue) {
      const maxAge = Number(attrValue);
      if (Number.isFinite(maxAge)) options.maxAge = maxAge;
    } else if (key === "samesite") {
      const sameSite = attrValue.toLowerCase();
      if (sameSite === "lax" || sameSite === "strict" || sameSite === "none") {
        options.sameSite = sameSite;
      }
    }
  }

  return { name, value, options };
}

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const target = new URL("/api/v1/auth/callback", `${API_PROXY_TARGET.replace(/\/$/, "")}/`);
  target.search = incoming.search;

  const upstream = await fetch(target, {
    method: "GET",
    headers: { Accept: "application/json" },
    redirect: "manual",
    cache: "no-store",
  });

  if (upstream.status >= 400) {
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "text/plain" },
    });
  }

  const location = upstream.headers.get("location") ?? `${incoming.origin}/`;
  const destination = new URL(location, incoming.origin);
  destination.searchParams.set("_auth", "1");

  const response = NextResponse.redirect(destination, 302);
  response.headers.set("cache-control", "no-store");

  for (const rawCookie of readSetCookies(upstream.headers)) {
    const parsed = parseCookie(rawCookie);
    if (!parsed) continue;
    response.cookies.set(parsed.name, parsed.value, parsed.options);
  }

  return response;
}
