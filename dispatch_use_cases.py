"""
Input Layer / Demo Dispatcher
--------------------------------
Run this script to explicitly trigger the exact use cases for the Hackathon showcase.
This clearly maps the problem statements ("Fix this error log", "Research this topic", etc.)
to their corresponding specialized agents.
"""

import sys
import json
import urllib.request

SOCKET_URL = "http://localhost:3000/api/task/assign"

def dispatch_task(task_description: str, agent_type: str):
    """Mocks standard task dispatch by printing the payload or hitting the server."""
    payload = {
        "taskId": f"demo-{agent_type}-101",
        "description": task_description,
        "agent_type": agent_type,
        "whiteboard": ""
    }
    
    print(f"\n======================================")
    print(f"👉 DISPATCHING USE CASE: {task_description.split(':')[0]}")
    print(f"======================================")
    print(f"[AGENT ROUTED] : {agent_type.upper()}")
    print(f"[FULL PROMPT]  : '{task_description}'\n")
    
    # Attempting to POST to running socket server
    try:
        req = urllib.request.Request(
            SOCKET_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req) as response:
            print(f"[RESULT] Success! Connected to orchestrator. Status: {response.getcode()}")
    except Exception as e:
        print(f"[INFO] Backend server is not running or accessible ({e}).")
        print("[INFO] Showing JSON payload that would have been dispatched:")
        print(json.dumps(payload, indent=2))

def fix_error_log_use_case():
    """Use Case 1: Fix this error log"""
    prompt = (
        "Fix this error log: \n"
        "Traceback (most recent call last):\n"
        "  File 'server.py', line 45, in <module>\n"
        "    db.connect(os.environ['DB_URL'])\n"
        "KeyError: 'DB_URL'"
    )
    dispatch_task(prompt, agent_type="debug")

def research_topic_use_case():
    """Use Case 2: Research this topic"""
    prompt = (
        "Research this topic: 'Optimization techniques for vector database index rebuilding.' "
        "Look into documentation and save the best insight to memory."
    )
    dispatch_task(prompt, agent_type="research")

def answer_support_ticket_use_case():
    """Use Case 3: Answer this support ticket"""
    prompt = (
        "Answer this support ticket: 'User states clicking the submit button freezes the page.' "
        "Navigate the UI and check the browser console for unhandled promise rejections."
    )
    dispatch_task(prompt, agent_type="orchestrator")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        print("OPTICON USE CASE ENTRY POINTS")
        print("1: Fix this error log")
        print("2: Research this topic")
        print("3: Answer this support ticket")
        choice = input("\nSelect a use case to dispatch (1/2/3): ")

    if choice == "1":
        fix_error_log_use_case()
    elif choice == "2":
        research_topic_use_case()
    elif choice == "3":
        answer_support_ticket_use_case()
    else:
        print("Invalid choice.")
