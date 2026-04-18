import { NextResponse } from "next/server";
import { v4 as uuidv4 } from "uuid";
import { createSession, addTodos, getSession } from "@/lib/session-store";
import { auth } from "@/auth";
import { getMaxAgentsForUser } from "@/lib/billing";

export const dynamic = "force-dynamic";
import {
  persistSession,
  persistTodos,
  persistSessionStatus,
} from "@/lib/db/session-persist";
import { decomposeTasks, type DecomposedTask } from "@/lib/orchestrator";

const isDemoMode = process.env.BYPASS_AUTH?.toLowerCase() === "true" || !process.env.DATABASE_URL || process.env.DATABASE_URL.includes("placeholder");

export async function POST(request: Request) {
  let userId = "demo-user";

  if (!isDemoMode) {
    const authSession = await auth();
    if (!authSession?.user?.id) {
      console.log("[sessions] Auth failed. isDemoMode:", isDemoMode, "BYPASS_AUTH:", process.env.BYPASS_AUTH);
      return NextResponse.json({ error: `Unauthorized (isDemoMode=${isDemoMode})` }, { status: 401 });
    }
    userId = authSession.user.id;
  }

  const body = await request.json();
  const { prompt, agentCount } = body as {
    prompt: string;
    agentCount: number;
  };

  if (!prompt || typeof prompt !== "string" || prompt.trim().length === 0) {
    return NextResponse.json({ error: "Prompt is required" }, { status: 400 });
  }

  if (
    !agentCount ||
    typeof agentCount !== "number" ||
    agentCount < 1 ||
    agentCount > 4
  ) {
    return NextResponse.json(
      { error: "agentCount must be between 1 and 4" },
      { status: 400 },
    );
  }

  if (!isDemoMode) {
    const maxAgents = await getMaxAgentsForUser(userId);
    if (agentCount > maxAgents) {
      return NextResponse.json(
        {
          error: `Your plan allows up to ${maxAgents} agents.`,
          code: "PLAN_LIMIT_EXCEEDED",
          maxAgents,
        },
        { status: 403 },
      );
    }
  }

  const sessionId = uuidv4();
  createSession(sessionId, prompt.trim(), agentCount, userId);

  // Persist session to database (skip in demo mode)
  if (!isDemoMode) {
    persistSession(
      sessionId,
      userId,
      prompt.trim(),
      agentCount,
      "decomposing"
    ).catch(console.error);
  }

  // Decompose prompt into TODOs via Dedalus
  let todoDescriptions: DecomposedTask[];
  try {
    todoDescriptions = await decomposeTasks(prompt.trim(), agentCount);
  } catch (error: any) {
    console.error("[orchestrator] Critical error in decomposition:", error);
    const errorMsg = error instanceof Error ? error.message : String(error);
    const failedSession = getSession(sessionId);
    if (failedSession) failedSession.status = "failed";
    return NextResponse.json(
      { error: `Planner failed. Using fallback execution... (Internal error: ${errorMsg})` },
      { status: 500 },
    );
  }

  // Add TODOs to session — do NOT start workers yet
  const todos = addTodos(sessionId, todoDescriptions);

  // Persist todos to database
  if (!isDemoMode) {
    persistTodos(sessionId, todos).catch(console.error);
  }

  // Set session to pending_approval so the user can review tasks
  const opticonSession = getSession(sessionId);
  if (opticonSession) {
    opticonSession.status = "pending_approval";
    // Persist status update
    if (!isDemoMode) {
      persistSessionStatus(sessionId, "pending_approval").catch(console.error);
    }
  }

  return NextResponse.json({ sessionId, tasks: todos }, { status: 201 });
}
