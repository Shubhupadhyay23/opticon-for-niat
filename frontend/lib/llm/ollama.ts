/**
 * Lightweight Ollama client for Node.js (Frontend)
 */

interface OllamaMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface OllamaChatOptions {
  model?: string;
  temperature?: number;
  max_tokens?: number;
}

export async function ollamaChat(
  messages: OllamaMessage[],
  options: OllamaChatOptions = {}
): Promise<string> {
  const baseUrl = process.env.LLM_BASE_URL || "http://localhost:11434";
  const model = options.model || process.env.LLM_MODEL || "llama3.1";

  console.log(`[ollama-client] Calling ${baseUrl} with model ${model}`);

  try {
    const response = await fetch(`${baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: model,
        messages: messages,
        temperature: options.temperature ?? 0.1,
        max_tokens: options.max_tokens ?? 2048,
        stream: false,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Ollama Error (${response.status}): ${errorText}`);
    }

    const data = await response.json();
    return data.choices?.[0]?.message?.content || "";
  } catch (error) {
    console.error("[ollama-client] Request failed:", error);
    throw error;
  }
}
