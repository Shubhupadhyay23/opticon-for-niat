import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { getSession, restoreSessionFromDb } from "@/lib/session-store";
import { getSessionWithDetails, persistSessionStatus } from "@/lib/db/session-persist";
import { respawnWorker } from "@/lib/worker-manager";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const isDemoMode = process.env.BYPASS_AUTH?.toLowerCase() === "true" || !process.env.DATABASE_URL || process.env.DATABASE_URL.includes("placeholder");
  
  if (!isDemoMode) {
    const authSession = await auth();
    if (!authSession?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // If already in memory, just return it
    const existing = getSession(id);
    if (existing) {
      return NextResponse.json(existing);
    }

    // Try to recover from database
    const dbSession = await getSessionWithDetails(id);
    if (!dbSession) {
      return NextResponse.json({ error: "Session not found" }, { status: 404 });
    }

    if (dbSession.userId !== authSession.user.id) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }
    
    // Restore in-memory state
    const restored = restoreSessionFromDb(dbSession);
    return NextResponse.json(restored);
  }

  // Demo mode: just return from memory
  const existing = getSession(id);
  if (!existing) {
    return NextResponse.json({ error: "Session not found" }, { status: 404 });
  }

  return NextResponse.json(existing);
}
