import { auth } from "@/auth";
import { NextResponse } from "next/server";

const isDemoMode = !process.env.DATABASE_URL || process.env.DATABASE_URL.includes("placeholder");

export default isDemoMode
  ? function demoMiddleware() {
      // No auth enforcement in demo mode — let everything through
      return NextResponse.next();
    }
  : auth((req) => {
      const { pathname } = req.nextUrl;

      const isAuthenticated = !!req.auth;

      // Allow auth pages, auth API, demo mode, and static assets
      const isPublic =
        pathname.startsWith("/auth/") ||
        pathname.startsWith("/api/auth/") ||
        pathname.startsWith("/api/flowglad/") ||
        pathname.startsWith("/session/demo") ||
        pathname.startsWith("/_next/") ||
        pathname.startsWith("/favicon") ||
        pathname === "/pricing" ||
        pathname === "/api/health";

      if (isPublic) return;

      if (!isAuthenticated) {
        const signInUrl = new URL("/auth/signin", req.url);
        signInUrl.searchParams.set("callbackUrl", pathname);
        return Response.redirect(signInUrl);
      }
    });

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
