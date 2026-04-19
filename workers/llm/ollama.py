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
        msg = {
            "role": m.get("role", "user"),
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

    try:
        url = f"{base_url}/api/chat"
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
            logger.error(f"Ollama API error: {response.status_code} - {response.text}")
            raise Exception(f"Ollama error: {response.text}")
            
        result = response.json()
        return result.get("message", {}).get("content", "")
        
    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to Ollama. Is it running? (ollama serve)")
        raise Exception("Ollama connection refused. Please start Ollama locally.")
    except Exception as e:
        logger.exception("Error during Ollama chat call")
        raise
