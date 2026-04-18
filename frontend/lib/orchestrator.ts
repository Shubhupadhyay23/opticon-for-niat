import { Dedalus } from "dedalus-labs";

const client = new Dedalus({
  apiKey: process.env.DEDALUS_API_KEY,
});

/** A single task with its lane assignment from the orchestrator. */
export interface DecomposedTask {
  description: string;
  lane: number;
}

/**
 * Extract the first valid JSON object from a string by tracking balanced braces.
 * Handles cases where LLM returns reasoning text before/after the JSON.
 */
function extractJSON(text: string): string {
  // First try: extract from markdown code blocks
  const codeBlockMatch = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (codeBlockMatch) {
    return codeBlockMatch[1].trim();
  }

  const start = text.indexOf("{");
  if (start === -1) throw new Error("No JSON object found in response");

  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (escaped) { escaped = false; continue; }
    if (ch === "\\") { escaped = true; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (inString) continue;

    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  throw new Error("Unbalanced braces in JSON response");
}

/**
 * Internal helper to call Dedalus with a timeout and specific prompt.
 */
async function callPlanner(
  prompt: string,
  systemInstruction: string,
  userInstruction: string,
  timeoutMs: number = 15000
): Promise<string> {
  const llmCall = client.chat.completions.create({
    model: "anthropic/claude-sonnet-4-5-20250929",
    max_tokens: 4096,
    messages: [
      { role: "system", content: systemInstruction },
      { role: "user", content: `${userInstruction}\n\nTask: ${prompt.trim()}` },
    ],
  });

  const timeout = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error("Planner timed out")), timeoutMs)
  );

  const response = await Promise.race([llmCall, timeout]);
  return response.choices[0].message.content || "";
}

/**
 * Decompose a prompt into granular tasks using a fault-tolerant multi-stage pipeline.
 */
export async function decomposeTasks(
  prompt: string,
  taskCount?: number,
  maxTasks: number = 10,
  maxLanes: number = 4
): Promise<DecomposedTask[]> {
  const countDesc = taskCount ? `exactly ${taskCount}` : `up to ${maxTasks}`;

  const standardSystem = `You are a JSON API that decomposes user requests into executable steps. You respond with raw JSON only, never natural language. Return ONLY valid JSON. No explanations.`;

  const standardUser = `Decompose the following task into ${countDesc} granular, executable steps grouped into parallel lanes. 
STRICT JSON FORMAT:
{
  "tasks": [
    { "description": string, "lane": number }
  ]
}`;

  const retryUser = `Break this into simple, granular steps:`;

  // STAGE 1: Primary Attempt
  try {
    console.log("[orchestrator:planner] Attempting primary decomposition...");
    const text = await callPlanner(prompt, standardSystem, standardUser);
    return parseResult(text, maxTasks, maxLanes);
  } catch (error) {
    console.warn("[orchestrator:retry] Primary attempt failed. Retrying with simplified prompt...", error instanceof Error ? error.message : error);

    // STAGE 2: Simplified Retry
    try {
      const text = await callPlanner(prompt, standardSystem, retryUser);
      return parseResult(text, maxTasks, maxLanes);
    } catch (retryError) {
      console.error("[orchestrator:failover] Both attempts failed. Using fallback mode.", retryError instanceof Error ? retryError.message : retryError);

      // STAGE 3: Final Fallback (Mandatory)
      return [{
        description: prompt.trim(),
        lane: 0,
      }];
    }
  }
}

/**
 * Parser that handles various schema shapes and validates content.
 */
function parseResult(text: string, maxTasks: number, maxLanes: number): DecomposedTask[] {
  console.log("[orchestrator:parser] Processing LLM response...");
  const json = extractJSON(text);
  const parsed = JSON.parse(json);

  // Schema Validation (Step 4): Handle both "tasks" and "todos" keys
  const rawTasks = parsed.tasks || parsed.todos;

  if (!rawTasks || !Array.isArray(rawTasks) || rawTasks.length === 0) {
    throw new Error("No valid task list found in JSON response");
  }

  const tasks: DecomposedTask[] = rawTasks
    .slice(0, maxTasks)
    .map((t: any) => ({
      description: String(t.description || t.task || t.command || "Execute task"),
      lane: Math.min(Number(t.lane ?? 0), maxLanes - 1),
    }));

  console.log(`[orchestrator:parser] Successfully parsed ${tasks.length} tasks.`);
  return tasks;
}
