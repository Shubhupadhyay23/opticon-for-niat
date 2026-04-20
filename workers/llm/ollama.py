import requests
import json
import logging
import base64

logger = logging.getLogger(__name__)

def ollama_chat(messages, model="llama3.1", base_url="http://localhost:11434"):
    """
    Ollama API wrapper that supports vision and chat history.
    Uses the /api/chat endpoint.
    """
    formatted_messages = []
    
    for m in messages:
        role = m.get("role", "user")
        print(f"DEBUG: Processing message role: {role}", flush=True)
        msg = {
            "role": role,
            "content": ""
        }
        
        content = m.get("content", "")
        if isinstance(content, str):
            msg["content"] = content
        elif isinstance(content, list):
            # Handle multimodal content (screenshots)
            images = []
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "image_url":
                        url = item.get("image_url", {}).get("url", "")
                        if url.startswith("data:image"):
                            # Extract base64 part
                            b64 = url.split(",")[1]
                            images.append(b64)
                elif isinstance(item, str):
                    text_parts.append(item)
            
            msg["content"] = "\n".join(text_parts)
            if images:
                msg["images"] = images
        
        formatted_messages.append(msg)

    print(f"=== OLLAMA CHAT START === (Model: {model})", flush=True)
    
    # Standardize URL: strip trailing /v1 if present and ensure no trailing slash
    clean_base = base_url.replace("/v1", "").rstrip("/")
    url = f"{clean_base}/api/chat"
    
    try:
        payload = {
            "model": model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "temperature": 0
            }
        }
        
        response = requests.post(url, json=payload, timeout=90)
        
        if response.status_code != 200:
            print(f"=== OLLAMA ERROR: {response.status_code} ===", flush=True)
            logger.error(f"Ollama API error: {response.status_code} - {response.text}")
            raise Exception(f"Ollama error: {response.text}")
            
        result = response.json()
        content = result.get("message", {}).get("content", "")
        print(f"=== OLLAMA OUTPUT RECEIVED ({len(content)} chars) ===", flush=True)
        return content
        
    except requests.exceptions.ConnectionError:
        logger.error(f"Could not connect to Ollama at {url}. Is it running? (ollama serve)")
        raise Exception(f"Ollama connection refused at {url}. If running on Railway, you MUST set LLM_BASE_URL to a public tunnel (like ngrok).")
    except Exception as e:
        logger.exception("Error during Ollama chat call")
        raise
