import logging
import json
import e2b_tools

logger = logging.getLogger(__name__)

def run_tool(response):
    """
    Parses a string response for 'TOOL: name' and 'INPUT: json' format
    and executes the tool. If no tool is found, returns the original response.
    """
    if "TOOL:" in response:
        try:
            lines = response.split("\n")
            tool_name = ""
            tool_input = ""
            
            for line in lines:
                if line.startswith("TOOL:"):
                    tool_name = line.replace("TOOL:", "").strip()
                elif line.startswith("INPUT:"):
                    tool_input = line.replace("INPUT:", "").strip()
            
            if tool_name:
                print(f"=== TOOL START: {tool_name} ===", flush=True)
                logger.info(f"🛠 Dispatching tool: {tool_name} with input: {tool_input}")
                try:
                    args = json.loads(tool_input) if tool_input else {}
                except:
                    args = {"text": tool_input} # Fallback for non-JSON input
                
                result = e2b_tools.execute_tool(tool_name, args)
                print(f"=== TOOL FINISHED: {tool_name} ===", flush=True)
                return result
        except Exception as e:
            logger.error(f"Failed to dispatch tool: {e}")
            return f"ERROR: Tool dispatch failed: {e}"
            
    return response

def map_tool_call_to_dispatcher(tool_call):
    """
    Converts a standard OpenAI/Dedalus tool call object into a 
    dispatcher-friendly format if needed.
    """
    name = tool_call.function.name
    args = tool_call.function.arguments
    return f"TOOL:{name}\nINPUT:{args}"
