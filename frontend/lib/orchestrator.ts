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
 * Decompose a prompt into granular, step-by-step tasks grouped into parallel
 * lanes using Claude Sonnet via the Dedalus Labs API.
 */
export async function decomposeTasks(
  prompt: string,
  taskCount?: number,
  maxTasks: number = 10,
  maxLanes: number = 4,
): Promise<DecomposedTask[]> {
  const countInstruction = taskCount
    ? `exactly ${taskCount}`
    : `as many as needed (minimum 1, maximum ${maxTasks})`;

  try {
    console.log("[orchestrator:planner] Sending prompt to Dedalus...");
    const response = await client.chat.completions.create({
      model: "anthropic/claude-sonnet-4-5-20250929",
      max_tokens: 4096,
      messages: [
        {
          role: "system",
          content: `You are a JSON API that breaks user requests into small, simple, granular tasks grouped into parallel lanes. You respond with raw JSON only, never natural language.

Each lane is assigned to one AI agent on its own cloud desktop with a browser and terminal. Tasks within a lane run sequentially. Different lanes run in parallel.

Deciding lanes:
- Use same lane for tasks that share state or depend on each other.
- Use separate lanes only for independent work.
- Maximum ${maxLanes} lanes.

Bias toward simplicity and granularity. Each task should be ONE simple action.
End each task by describing how the agent knows it's done.`,
        },
        {
          role: "user",
          content: `Break the following request into ${countInstruction} small, granular tasks grouped into lanes. Each task should be a simple, concrete action. 

Request: ${prompt.trim()}

Return a JSON object with a "todos" array where each item has:
- "description": the task instruction
- "lane": integer lane number (starting from 0)`,
        },
      ],
    });

    const text = response.choices[0].message.content || "";
    console.log("[orchestrator:parser] Raw response received.");

    try {
      const json = extractJSON(text);
      const parsed = JSON.parse(json);

      if (!parsed.todos || !Array.isArray(parsed.todos)) {
        throw new Error("Missing 'todos' array in parsed JSON");
      }

      const tasks: DecomposedTask[] = parsed.todos
        .slice(0, maxTasks)
        .map((t: any) => ({
          description: String(t.description || t.task || "Process task"),
          lane: Math.min(Number(t.lane ?? 0), maxLanes - 1),
        }));

      if (tasks.length === 0) throw new Error("Parsed 'todos' array is empty");

      console.log(`[orchestrator:parser] Successfully parsed ${tasks.length} tasks.`);
      return tasks;
    } catch (parseError) {
      console.error("[orchestrator:parser] Failed to parse LLM response:", parseError);
      throw parseError; // Caught by outer block
    }
  } catch (error) {
    console.warn("[orchestrator:failover] Decomposition failed. Using fallback single-task mode.", error);
    // FALLBACK: Return the original prompt as a single task in lane 0
    return [{
      description: prompt.trim(),
      lane: 0
    }];
  }
}
