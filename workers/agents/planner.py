import json
import logging
from llm.ollama import ollama_chat

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """
You are a Planning Agent for a desktop automation system.
Your job is to break down the user's high-level goal into a sequence of specific, actionable sub-tasks.

You will be given the user's goal.
Return ONLY a JSON object in this format:
{
  "tasks": [
    {
      "id": 1,
      "description": "Short, clear description of what to do (e.g., 'Open Chrome and navigate to Google')",
      "agent_type": "orchestrator"
    },
    ...
  ]
}

Available Agent Types:
- orchestrator: For general desktop interaction.
- debug: For terminal/log analysis.
- research: For searching documentation.

Rules:
1. Be specific but concise.
2. Ensure tasks are in logical order.
3. Return ONLY the JSON object, NO other text.
"""

def create_plan(user_input, model="llama3.1"):
    print("=== PLANNER START ===", flush=True)
    print(f"Goal: {user_input}", flush=True)
    logger.info("🧠 Planning task: %s", user_input)
    response = ollama_chat([
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": user_input}
    ], model=model)
    
    print(f"=== PLANNER OUTPUT ===\n{response}\n====================", flush=True)
    
    try:
        # Clean up any potential markdown formatting
        cleaned = response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
            
        return json.loads(cleaned)
    except Exception as e:
        logger.error(f"Failed to parse plan JSON: {e}. Raw response: {response}")
        # Fallback to a single-task plan
        return {
            "tasks": [
                {"id": 1, "description": user_input, "agent_type": "orchestrator"}
            ]
        }
