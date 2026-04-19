import asyncio
import base64
import json
import logging
import os
import sys
import time
from io import BytesIO

import socketio
from e2b_desktop import Sandbox
from dedalus_labs import AsyncDedalus
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import e2b_tools
from memory import MemoryManager
from replay import ReplayBuffer
from agents import AGENT_PROFILES

logger = logging.getLogger(__name__)

# MODEL = "openai/gpt-4o-mini"
MODEL = "claude-3-5-sonnet-20241022"  # Correct model name for Anthropic
ENABLE_MOCK_LLM = os.environ.get("ENABLE_MOCK_LLM", "false").lower() == "true"
MAX_STEPS = 500
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1  # seconds
HISTORY_KEEP_RECENT = 10  # number of recent screenshot/action exchanges to keep verbatim
THUMBNAIL_INTERVAL_SECONDS = 10
MIN_STEPS_BEFORE_DONE = 3  # agent must take at least this many actions before calling done
CHECKPOINT_INTERVAL = 100  # Pause every N steps for user check-in (Slack only)


def make_screenshot_message():
    """Capture the desktop and return (message_dict, raw_png_bytes)."""
    raw_bytes = e2b_tools.screenshot_raw_bytes()

    # Compress PNG to JPEG for smaller API payloads (~500KB-1MB vs 2-8MB)
    img = Image.open(BytesIO(raw_bytes))
    # Reduce quality for smoother UI streaming (60 is the sweet spot for speed vs clarity)
    jpeg_buf = BytesIO()
    img.save(jpeg_buf, format="JPEG", quality=60)
    jpeg_b64 = base64.b64encode(jpeg_buf.getvalue()).decode("utf-8")

    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "Here is the current screenshot of the desktop:"},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{jpeg_b64}",
                    "detail": "high",
                },
            },
            {"type": "text", "text": "What action should you take next?"},
        ],
    }
    return msg, raw_bytes  # Still return raw PNG for replay buffer


async def call_with_retry(client, **kwargs):
    """Call client.chat.completions.create() with exponential backoff on failure."""
    
    if ENABLE_MOCK_LLM:
        print("⚡ [MOCK] Bypassing real LLM call...", flush=True)
        await asyncio.sleep(1)
        # Construct a fake response object matching Dedalus/OpenAI schema
        from types import SimpleNamespace
        return SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(
                content="I will complete the task.",
                tool_calls=[SimpleNamespace(id="mock_1", function=SimpleNamespace(name="done", arguments="{}"))]
            ))
        ])

    for attempt in range(MAX_RETRIES):
        try:
            # Prevent hangs from legacy/future model experiments
            current_model = kwargs.get('model', '')
            if "2025" in current_model:
                raise ValueError(f"❌ Invalid / Future Model detected: {current_model}")

            print(f"🧠 FULL KWARGS: {kwargs}", flush=True)
            print(f"  (attempt {attempt + 1}/{MAX_RETRIES}) Calling LLM: {current_model}...", flush=True)
            
            # Hard 30s timeout for isolation
            response = await asyncio.wait_for(client.chat.completions.create(**kwargs), timeout=30.0)
            
            print("✅ LLM response received", flush=True)
            return response
        except asyncio.TimeoutError:
            print(f"❌ LLM TIMEOUT after 20s (Attempt {attempt + 1})", flush=True)
            if attempt == MAX_RETRIES - 1:
                raise
        except Exception as e:
            print(f"💥 RAW ERROR: {repr(e)}", flush=True)
            if attempt == MAX_RETRIES - 1:
                raise
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            print(f"⚠️ Retrying in {delay}s...", flush=True)
            await asyncio.sleep(delay)


def trim_message_history(messages):
    """Keep system + task messages and only the last N exchanges.

    The message list follows a repeating pattern after the first two entries
    (system, task):
        user (screenshot) -> assistant (tool call) -> tool (result)
    Each group of 3 is one "exchange".  We keep the first 2 messages (system
    prompt + task description) plus the most recent HISTORY_KEEP_RECENT
    exchanges verbatim. Older exchanges are replaced by a single compact
    text summary so the model retains awareness of what it already did
    without the cost of carrying base64 screenshots.
    """
    prefix_len = 2  # system + task
    body = messages[prefix_len:]
    exchange_size = 3  # screenshot msg, assistant msg, tool result msg
    keep_count = HISTORY_KEEP_RECENT * exchange_size

    if len(body) <= keep_count:
        return  # nothing to trim

    old_part = body[: len(body) - keep_count]
    recent_part = body[len(body) - keep_count:]

    # Build a compact summary of old exchanges
    summaries = []
    for msg in old_part:
        role = msg.get("role", "")
        if role == "assistant":
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function", {})
                summaries.append(f"- {fn.get('name', '?')}({fn.get('arguments', '')})")
        elif role == "tool":
            content = msg.get("content", "")
            if content:
                summaries.append(f"  -> {content[:120]}")

    summary_text = (
        f"[History summary: you already performed {len(old_part) // exchange_size} "
        f"actions on this task. Recent actions:\n"
        + "\n".join(summaries[-20:])  # keep last 20 summary lines to stay compact
        + "\n]"
    )

    messages[prefix_len:] = [
        {"role": "user", "content": summary_text},
    ] + recent_part


async def run_agent_loop(client, task_description, whiteboard_content="", user_memories="", on_step=None, replay_buffer=None, terminated=None, on_screenshot=None, on_checkpoint=None, agent_type="orchestrator"):
    """
    Observe-think-act loop using Dedalus chat.completions.create().
    """
    print("🧠 ENTERED run_agent_loop", flush=True)
    profile = AGENT_PROFILES.get(agent_type, AGENT_PROFILES["orchestrator"])
    system_content = profile["prompt"]
    if whiteboard_content:
        system_content += (
            f"\n\nShared whiteboard (written by other agents):\n{whiteboard_content}"
        )
    if user_memories:
        system_content += f"\n\n{user_memories}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"Your task: {task_description}"},
    ]

    last_action_label = "Starting task"
    no_tool_retries = 0
    raw_png = None  # Track latest screenshot for checkpoint thumbnails

    for step in range(MAX_STEPS):
        # Check for termination between steps
        if terminated is not None and terminated.is_set():
            print(f"Terminated during task at step {step}", flush=True)
            return "(terminated by user)"

        print(f"🚀 ENTERED AGENT LOOP TURN {step + 1}", flush=True)

        # Checkpoint: pause every CHECKPOINT_INTERVAL steps for Slack check-in
        if on_checkpoint and step > 0 and step % CHECKPOINT_INTERVAL == 0:
            result = await on_checkpoint(step, raw_png)
            if result == "terminated":
                return "(terminated by user at checkpoint)"

        # Trim old exchanges to keep context window lean
        trim_message_history(messages)

        # Observe: take screenshot and show it to the model
        screenshot_msg, raw_png = make_screenshot_message()
        messages.append(screenshot_msg)

        # Capture frame for replay
        if replay_buffer is not None:
            replay_buffer.capture_frame(raw_png, last_action_label)

        # Emit thumbnail if callback provided
        if on_screenshot is not None:
            await on_screenshot(raw_png)

        # Filter allowed tools for this sub-agent and exclude 'done' early on
        allowed_tool_names = set(profile["tools"])
        if step < MIN_STEPS_BEFORE_DONE:
            allowed_tool_names.discard("done")
            
        tools = [t for t in e2b_tools.TOOL_SCHEMAS if t["function"]["name"] in allowed_tool_names]

        # Emit "Thinking" state immediately with model info
        if on_step:
            await on_step(step + 1, "thinking", {}, f"Calling model {MODEL}...")

        try:
            print("🧠 BEFORE LLM...", flush=True)
            response = await asyncio.wait_for(
                call_with_retry(
                    client,
                    model=MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice={"type": "any"},
                    max_tokens=2048,
                ),
                timeout=60.0  # Hard timeout for LLM reasoning
            )
            print("✅ AFTER LLM", flush=True)
        except asyncio.TimeoutError:
            print("❌ LLM TIMEOUT after 60s", flush=True)
            if on_step:
                await on_step(step + 1, "error", {"error": "LLM timeout"}, "Thinking took too long, retrying...")
            continue
        except Exception as e:
            print(f"❌ LLM ERROR: {e}")
            raise

        choice = response.choices[0]
        msg = choice.message

        # Append assistant response to history
        messages.append(msg.to_dict() if hasattr(msg, "to_dict") else {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in (msg.tool_calls or [])
            ],
        })

        # Extract reasoning from assistant message content (Claude's thinking)
        reasoning = None
        if msg.content:
            if isinstance(msg.content, str):
                reasoning = msg.content.strip() or None
            elif isinstance(msg.content, list):
                text_parts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in msg.content
                    if (isinstance(block, dict) and block.get("type") == "text") or isinstance(block, str)
                ]
                combined = " ".join(text_parts).strip()
                reasoning = combined or None

        if not msg.tool_calls:
            print("❌ No tool call from LLM", flush=True)
            no_tool_retries += 1
            if no_tool_retries >= 3:
                logger.error("Model returned no tool calls %d times, giving up", no_tool_retries)
                return msg.content or "(model failed to call tools)"
            # Model returned no tool calls despite tool_choice — retry with a nudge
            logger.warning("No tool calls in response at step %d (retry %d/3)", step, no_tool_retries)
            messages.append({
                "role": "user",
                "content": "You must use one of the provided tools to continue (e.g., click, type_text, or done if finished). Please respond with a tool call."
            })
            continue

        # Got a valid tool call — reset retry counter
        no_tool_retries = 0

        # Execute the first tool call (one action per turn)
        tc = msg.tool_calls[0]
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}

        if on_step:
            await on_step(step + 1, name, args, reasoning)

        last_action_label = f"Tool: {name}"

        result = e2b_tools.execute_tool(name, args)

        # Self-Correction Interceptor
        if isinstance(result, str) and result.startswith("ERROR:"):
            logger.warning(f"Self-correction triggered: Tool {name} returned an error.")
            result += "\n\n[SYSTEM SELF-CORRECTION]: Your previous action failed. Do not blindly repeat it. Reassess the situation, try a different approach, or use the 'replan_strategy' or 'escalate_to_reviewer' tools."

        # If done, return the summary
        if name == "done":
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            return result

        # Append tool result and continue
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "(max steps reached)"


async def main():
    session_id = os.environ["SESSION_ID"]
    agent_id = os.environ["AGENT_ID"]
    user_id = os.environ.get("USER_ID")
    socket_url = os.environ.get("SOCKET_URL", "http://localhost:3000")

    logging.basicConfig(
        level=logging.INFO,
        format=f"[%(levelname)s] agent-{agent_id}: %(message)s",
    )

    # --- Socket.io connection ---
    sio = socketio.AsyncClient()
    await sio.connect(socket_url)

    async def emit(event, data):
        await sio.emit(event, {"sessionId": session_id, "agentId": agent_id, **data})

    # --- Register event handlers BEFORE booting sandbox ---
    task_queue = asyncio.Queue()
    terminated = asyncio.Event()
    force_kill = False

    print("🔌 Connected to socket server", flush=True)
    # Give the user immediate feedback that the worker has started
    await emit("agent:thinking", {"action": "Initializing worker", "detail": "Starting secure sandbox environment..."})

    @sio.on("disconnect")
    async def on_disconnect():
        print("🔌 Disconnected from socket server", flush=True)

    @sio.on("task:assign")
    async def on_task_assign(data):
        print("📥 TASK RECEIVED:", data.get("taskId", "unknown"), flush=True)
        await task_queue.put(data)

    @sio.on("task:none")
    async def on_task_none(data=None):
        terminated.set()

    @sio.on("session:stop")
    async def on_session_stop(data=None):
        nonlocal force_kill
        force_kill = True
        terminated.set()

    @sio.on("session:complete")
    async def on_session_complete(data=None):
        terminated.set()

    # Checkpoint resume signal (Slack user clicked Continue)
    checkpoint_resume = asyncio.Event()

    @sio.on("session:checkpoint_resume")
    async def on_checkpoint_resume(data=None):
        checkpoint_resume.set()

    # Join session room (Handlers registered first to prevent race conditions)
    await emit("agent:join", {})

    # --- Boot or reconnect E2B sandbox ---
    desktop = None
    reconnect_sandbox_id = os.environ.get("SANDBOX_ID")
    try:
        if reconnect_sandbox_id:
            try:
                print(f"🔄 Attempting to reconnect to sandbox {reconnect_sandbox_id}...", flush=True)
                desktop = Sandbox(sandbox_id=reconnect_sandbox_id, timeout=3600)
                desktop.stream.start()
                stream_url = desktop.stream.get_url()
                await emit("agent:stream_ready", {"streamUrl": stream_url})
                print(f"✅ Reconnected to sandbox {reconnect_sandbox_id}", flush=True)
            except Exception as e:
                print(f"⚠️ Reconnection failed (sandbox probably expired): {e}. Spawning new sandbox...", flush=True)
                desktop = None # Fall through to creation logic
        
        if not desktop:
            # Pass resolution to reduce streaming overhead on low-tier infra
            # Typically supported via kargs in newer e2b-desktop or environmental overrides
            # We'll try to set the resolution here
            desktop = Sandbox.create(timeout=3600)
            
            # Fallback: force resolution via xrandr inside the sandbox if needed
            try:
                desktop.run_command("xrandr --size 1280x720")
            except:
                pass
            # Immediate stream start - don't wait for anything else
            desktop.stream.start()
            # Restore 3s buffer for stream to stabilize
            time.sleep(3)
            
            # Emit sandbox_ready IMMEDIATELY
            await emit("agent:sandbox_ready", {"sandboxId": desktop.sandbox_id})
            
            print(f"✅ Sandbox created: {desktop.sandbox_id}. Initializing stream...", flush=True)
            stream_url = desktop.stream.get_url()
            await emit("agent:stream_ready", {"streamUrl": stream_url})
            print(f"✅ Stream active at {stream_url}", flush=True)
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Failed to boot/reconnect sandbox: {e}", flush=True)
        if reconnect_sandbox_id:
            await emit("agent:sandbox_expired", {})
        else:
            await emit("agent:error", {"error": str(e)})
        await sio.disconnect()
        return

    # --- Init tools ---
    e2b_tools.init(desktop)

    # --- Init Daedalus client ---
    dedalus_api_key = os.environ.get("DEDALUS_API_KEY")
    if not dedalus_api_key:
        print("❌ CRITICAL ERROR: DEDALUS_API_KEY is not set in environment!", flush=True)
    client = AsyncDedalus(api_key=dedalus_api_key)

    # --- Replay buffer ---
    replay_buffer = ReplayBuffer()
    r2_public_url = os.environ.get("R2_PUBLIC_URL", "")
    _last_thumbnail_time = 0.0

    # --- Memory manager (per-user, opt-in via ENABLE_MEMORY env var) ---
    memory_mgr = MemoryManager() if user_id and os.environ.get("ENABLE_MEMORY") else None

    # --- Heartbeat background task ---
    async def heartbeat_loop():
        while not terminated.is_set():
            try:
                await emit("agent:heartbeat", {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            except Exception:
                pass
            await asyncio.sleep(30)

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    # --- Thumbnail generation for Panopticon ---
    thumbnail_task = None

    async def generate_thumbnails():
        """Periodically capture and emit thumbnail screenshots for Panopticon."""
        while not terminated.is_set():
            try:
                # Take screenshot for thumbnail
                raw_bytes = e2b_tools.screenshot_raw_bytes()

                # Create smaller thumbnail (300x200 max)
                img = Image.open(BytesIO(raw_bytes))
                img.thumbnail((300, 200), Image.Resampling.LANCZOS)

                # Convert to JPEG and base64
                thumbnail_buf = BytesIO()
                img.save(thumbnail_buf, format="JPEG", quality=60)
                thumbnail_b64 = base64.b64encode(thumbnail_buf.getvalue()).decode("utf-8")

                # Emit thumbnail update
                await emit("agent:thumbnail", {
                    "thumbnail": thumbnail_b64,
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                })

                # Wait 10 seconds before next thumbnail
                await asyncio.sleep(10)

            except Exception as e:
                logger.warning("Failed to generate thumbnail: %s", e)
                await asyncio.sleep(5)  # Shorter delay on error

    # Start thumbnail generation task for Panopticon sessions
    is_panopticon = os.environ.get("PANOPTICON_MODE", "false").lower() == "true"
    if is_panopticon and os.environ.get("ENABLE_THUMBNAILS", "true").lower() == "true":
        thumbnail_task = asyncio.create_task(generate_thumbnails())

    try:
        while not terminated.is_set():
            # Wait for a task or termination signal
            try:
                task_data = await asyncio.wait_for(task_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                if terminated.is_set():
                    break
                print("⏳ Waiting for task...", flush=True)
                continue

            task_id = task_data["taskId"]
            task_description = task_data["description"]
            agent_type = task_data.get("agent_type", "orchestrator")
            whiteboard_content = task_data.get("whiteboard", "")

            print("🔥 EXECUTION TRIGGERED", flush=True)
            # Immediate feedback that worker is starting
            await emit("agent:thinking", {"action": "Agent started execution", "detail": task_description})
            
            await emit(
                "agent:thinking",
                {"action": "Starting task", "detail": task_description},
            )
            logger.info("🚀 Agent execution started for task %s: %s", task_id, task_description)

            # Retrieve user memories for context
            user_memories = ""
            if memory_mgr and user_id:
                user_memories = await asyncio.to_thread(
                    memory_mgr.retrieve_memories, user_id, task_description
                )

            async def on_step(step, name, args, reasoning=None):
                logger.info("  Step %d: %s(%s)", step, name, args)
                action_id = f"{agent_id}-{step}-{task_id}"
                # Emit reasoning BEFORE thinking so the server can attach it
                # to the buffered action before the throttle fires
                if reasoning:
                    await emit("agent:reasoning", {
                        "reasoning": reasoning,
                        "actionId": action_id,
                    })
                await emit("agent:thinking", {
                    "action": f"Tool: {name}",
                    "actionId": action_id,
                    "toolName": name,
                    "toolArgs": args,
                })

            async def on_screenshot(raw_png):
                nonlocal _last_thumbnail_time
                now = time.monotonic()
                if now - _last_thumbnail_time >= THUMBNAIL_INTERVAL_SECONDS:
                    _last_thumbnail_time = now
                    try:
                        thumb = ReplayBuffer.make_thumbnail(raw_png)
                        await emit("agent:thumbnail", {"thumbnail": thumb})
                    except Exception as e:
                        logger.warning("Failed to emit thumbnail: %s", e)

            # Checkpoint callback — only active for Slack sessions
            is_slack_session = os.environ.get("SLACK_SESSION") == "true"

            async def on_checkpoint(step, raw_png):
                """Emit checkpoint event and block until user responds."""
                thumb = ReplayBuffer.make_thumbnail(raw_png) if raw_png else None
                await emit("agent:checkpoint", {
                    "step": step,
                    "totalSteps": MAX_STEPS,
                    "thumbnail": thumb,
                })
                logger.info("Checkpoint at step %d — waiting for user", step)
                checkpoint_resume.clear()
                while not checkpoint_resume.is_set() and not terminated.is_set():
                    await asyncio.sleep(1.0)
                if terminated.is_set():
                    return "terminated"
                return "continue"

            # Execute the loop
            print(f"🚀 Execution started: {task_id[:8]}", flush=True)
            try:
                result = await run_agent_loop(
                    client, task_description,
                    whiteboard_content=whiteboard_content,
                    user_memories=user_memories,
                    on_step=on_step,
                    replay_buffer=replay_buffer,
                    terminated=terminated,
                    on_screenshot=on_screenshot,
                    on_checkpoint=on_checkpoint if is_slack_session else None,
                    agent_type=agent_type,
                )
            except (ConnectionError, TimeoutError, OSError) as e:
                # E2B sandbox expired or connection lost
                logger.error("Sandbox connection lost during task %s: %s", task_id, e)
                await emit("agent:sandbox_expired", {})
                terminated.set()
                result = f"(sandbox expired: {e})"
            except Exception as e:
                result = f"Error: {e}"
                await emit(
                    "agent:error",
                    {"error": str(e)},
                )
                logger.error("Task %s failed: %s", task_id, e)

            # Report task completion
            print(f"✅ Task finished: {task_id[:8]}", flush=True)
            await emit(
                "task:completed", {"todoId": task_id, "result": result}
            )
            logger.info("Completed task %s", task_id)

            # Store memories from successful tasks
            if memory_mgr and user_id and result and not result.startswith("("):
                await asyncio.to_thread(
                    memory_mgr.store_memories, user_id, task_description, result
                )

            # Write result to whiteboard
            await emit(
                "whiteboard:updated",
                {"content": f"## Agent {agent_id[:6]} - Task Complete\n{result}\n\n"},
            )

    finally:
        # Cancel heartbeat
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        # Save/upload replay frames before killing sandbox
        if replay_buffer.frame_count > 0:
            try:
                if r2_public_url:
                    # R2 mode: upload via presigned URLs
                    upload_result = await replay_buffer.upload_r2(
                        session_id, agent_id, socket_url, r2_public_url
                    )
                else:
                    # Local mode: save to disk, serve via API route
                    replay_dir = os.environ.get(
                        "REPLAY_DIR",
                        os.path.join(os.path.dirname(__file__), "..", "frontend", ".replays"),
                    )
                    serve_base = f"{socket_url}/api/replay/serve"
                    upload_result = replay_buffer.save_local(
                        session_id, agent_id, replay_dir, serve_base
                    )

                if upload_result:
                    manifest_url, frame_count = upload_result
                    await emit("replay:complete", {
                        "manifestUrl": manifest_url,
                        "frameCount": frame_count,
                    })
                    logger.info("Replay saved: %d frames", frame_count)
            except Exception as e:
                logger.error("Failed to save replay: %s", e)

        # Decide whether to pause or kill the sandbox
        if desktop:
            if force_kill:
                desktop.kill()
                logger.info("Sandbox killed (user-initiated stop)")
            else:
                try:
                    desktop.pause()
                    await emit("agent:paused", {"sandboxId": desktop.sandbox_id})
                    logger.info("Sandbox paused (id=%s)", desktop.sandbox_id)
                except Exception as e:
                    logger.warning("Failed to pause sandbox, killing instead: %s", e)
                    try:
                        desktop.kill()
                    except Exception:
                        pass
        await emit("agent:terminated", {})
        # Allow queued socket events (replay:complete, agent:terminated) to flush
        await asyncio.sleep(0.5)
        await sio.disconnect()
        logger.info("Worker shut down")


if __name__ == "__main__":
    asyncio.run(main())
