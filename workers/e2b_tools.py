import base64
import time

_sandbox = None


def init(sandbox):
    """Set the E2B sandbox instance used by all tool functions."""
    global _sandbox
    _sandbox = sandbox


# --- Tool functions (called by the agentic loop) ---

def screenshot_raw_bytes() -> bytes:
    """Take a screenshot and return raw PNG bytes."""
    return _sandbox.screenshot()


def screenshot_as_base64() -> str:
    """Take a screenshot and return base64-encoded PNG."""
    img_bytes = screenshot_raw_bytes()
    return base64.b64encode(img_bytes).decode("utf-8")


def click(x: int, y: int, button: str = "left", **_kwargs) -> str:
    """Click at screen coordinates (x, y)."""
    if button == "right":
        _sandbox.right_click(x, y)
    elif button == "middle":
        _sandbox.middle_click(x, y)
    else:
        _sandbox.left_click(x, y)
    time.sleep(0.5)
    return f"Clicked ({button}) at ({x}, {y})"


def double_click(x: int, y: int, **_kwargs) -> str:
    """Double-click at screen coordinates (x, y)."""
    _sandbox.double_click(x, y)
    return f"Double-clicked at ({x}, {y})"


def type_text(text: str) -> str:
    """Type the given text string. Newlines are typed as Enter key presses."""
    parts = text.split("\n")
    for i, part in enumerate(parts):
        if part:
            _sandbox.write(part)
            time.sleep(0.1)
        if i < len(parts) - 1:
            _sandbox.press("Enter")
            time.sleep(0.1)
    return f"Typed: {text}"


_KEY_ALIASES = {
    "return": "enter",
    "esc": "escape",
    "del": "delete",
    "bs": "backspace",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
}


def _normalize_key(key: str) -> str | list[str]:
    """Normalize key names and split combos like 'ctrl+c' into lists."""
    key = key.strip()
    # Handle combos: "ctrl+c", "alt+F2", "shift+enter"
    if "+" in key:
        parts = [_KEY_ALIASES.get(k.lower(), k.lower()) for k in key.split("+")]
        return parts
    return _KEY_ALIASES.get(key.lower(), key.lower())


def press_key(key: str, **_kwargs) -> str:
    """Press a key or key combo (e.g. 'enter', 'ctrl+c')."""
    time.sleep(0.2)
    normalized = _normalize_key(key)
    _sandbox.press(normalized)
    time.sleep(0.3)
    return f"Pressed: {normalized}"


def move_mouse(x: int, y: int) -> str:
    """Move the mouse cursor to screen coordinates (x, y) without clicking."""
    _sandbox.move_mouse(x, y)
    return f"Moved mouse to ({x}, {y})"


def scroll(x: int, y: int, direction: str = "down", amount: int = 3) -> str:
    """Scroll at screen coordinates (x, y) in the given direction."""
    _sandbox.move_mouse(x, y)
    _sandbox.scroll(direction=direction, amount=amount)
    time.sleep(0.5)
    return f"Scrolled {direction} by {amount} at ({x}, {y})"


# --- Outward integrations & System Tools ---

def send_slack_message(channel: str, message: str, **_kwargs) -> str:
    """Mock integration: send a message to a Slack channel."""
    return f"Successfully sent Slack message to {channel}: {message}"

def store_to_memory_db(key_insight: str, **_kwargs) -> str:
    """Store key findings to persistent memory/database."""
    return f"Key insight stored in database natively: {key_insight}"

def escalate_to_reviewer(reason: str, **_kwargs) -> str:
    """Pass control to Reviewer agent if confidence is low."""
    return f"Escalated to Reviewer Agent due to: {reason}"

def replan_strategy(new_plan: str, **_kwargs) -> str:
    """Explicitly reset instructions and set a new task plan."""
    return f"Replanned execution strategy: {new_plan}"

# --- Dispatch map: name -> function ---

TOOL_FUNCTIONS = {
    "click": click,
    "double_click": double_click,
    "type_text": type_text,
    "press_key": press_key,
    "move_mouse": move_mouse,
    "scroll": scroll,
    "send_slack_message": send_slack_message,
    "store_to_memory_db": store_to_memory_db,
    "escalate_to_reviewer": escalate_to_reviewer,
    "replan_strategy": replan_strategy,
}

# --- OpenAI-compatible tool schemas for chat.completions.create() ---
# No take_screenshot -- screenshots are injected automatically as user messages.

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click at screen coordinates (x, y). Defaults to left-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button (default: left)",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "double_click",
            "description": "Double-click at screen coordinates (x, y).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type the given text string on the keyboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a key or key combo (e.g. 'enter', 'ctrl+c', 'alt+F2').",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key or combo to press"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_mouse",
            "description": "Move the mouse cursor to screen coordinates (x, y) without clicking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll at screen coordinates (x, y) in a direction. Use for scrolling web pages, documents, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Direction to scroll",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Number of scroll steps (default 3)",
                    },
                },
                "required": ["x", "y", "direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Call this when the task is complete. Provide a structured output of your results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root_cause": {"type": "string", "description": "What was the core problem?"},
                    "fix": {"type": "string", "description": "What changes did you apply to resolve it?"},
                    "confidence": {"type": "string", "description": "Your numerical confidence score (e.g. '87%')"},
                    "action": {"type": "string", "description": "The final outcome action (e.g. 'PR created', 'Logs analyzed')"},
                    "steps_taken": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of distinct steps you took"
                    },
                },
                "required": ["root_cause", "fix", "confidence", "action", "steps_taken"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_slack_message",
            "description": "Send a message to a Slack channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Slack channel name (e.g. #general)"},
                    "message": {"type": "string", "description": "Message content"},
                },
                "required": ["channel", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_to_memory_db",
            "description": "Store an important key insight from your task into the memory database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_insight": {"type": "string", "description": "The insight or summary to memorize"},
                },
                "required": ["key_insight"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_reviewer",
            "description": "If your confidence is low or you cannot fix the bug, escalate the task to the Reviewer Agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for escalating to the reviewer"},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replan_strategy",
            "description": "If you are stuck and need to restart your approach, outline your new step-by-step strategy here.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_plan": {"type": "string", "description": "Your revised step-by-step plan"},
                },
                "required": ["new_plan"],
            },
        },
    },
]


def execute_tool(name, arguments):
    """Execute a tool by name with the given arguments dict. Returns result string.

    Errors are returned as strings so the model can self-correct rather than crashing.
    """
    if name == "done":
        if "root_cause" in arguments:
            steps_joined = ", ".join(arguments.get("steps_taken", []))
            return (
                f"Root Cause: {arguments.get('root_cause')}\n"
                f"Fix: {arguments.get('fix')}\n"
                f"Confidence: {arguments.get('confidence')}\n"
                f"Action: {arguments.get('action')}\n"
                f"Steps Taken: {steps_joined}"
            )
        return arguments.get("summary", "Task complete")
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return f"ERROR: Unknown tool '{name}'. Available tools: {', '.join(TOOL_FUNCTIONS.keys())}, done"
    try:
        return func(**arguments)
    except Exception as e:
        return f"ERROR: {name}({arguments}) failed — {e}. Please fix your arguments and try again."
