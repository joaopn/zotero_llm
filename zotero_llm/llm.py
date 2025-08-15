"""
LLM interaction module for Zotero LLM Assistant
Supports multiple LLM providers with hardcoded configurations
"""

import logging
import requests
import os
from typing import Dict, Any


# Provider configurations
PROVIDER_CONFIGS = {
    "local": {
        "api_key_required": False
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_required": True
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "api_key_required": True
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_required": True
    }
}


def call_llm(prompt: str, config: Dict[str, Any]) -> str:
    """
    Make LLM API call with proper error handling.
    Uses provider-specific configurations.
    
    Args:
        prompt: The prompt to send to the LLM
        config: Configuration dictionary
        
    Returns:
        LLM response text
    """
    llm_config = config.get('llm', {})
    
    # Get provider and validate
    provider = llm_config.get('provider', 'local')
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(f"Unknown provider: {provider}. Valid options: {list(PROVIDER_CONFIGS.keys())}")
    
    provider_config = PROVIDER_CONFIGS[provider]
    
    # Get common settings
    model = llm_config.get('model')
    max_tokens = llm_config.get('max_tokens')
    temperature = llm_config.get('temperature')
    top_p = llm_config.get('top_p')
    top_k = llm_config.get('top_k')
    min_p = llm_config.get('min_p')
    
    # Model is always required
    if not model:
        raise ValueError(f"Model is required for {provider}. Set model in config.yaml")
    
    # Handle base URL based on provider
    if provider == 'local':
        # For local provider, port is required
        port = llm_config.get('port')
        if not port:
            raise ValueError("Port is required for local provider. Set port in config.yaml")
        base_url = f"http://localhost:{port}/v1"
        logging.info(f"Using local provider on port {port} with model: {model}")
    else:
        # For remote providers, use predefined base URL
        base_url = provider_config['base_url']
        logging.info(f"Using {provider} provider with model: {model}")
    
    # Handle API key based on provider requirements
    api_key = llm_config.get('api_key') or os.getenv('LLM_API_KEY')
    
    if provider_config['api_key_required']:
        if not api_key:
            raise ValueError(f"API key required for {provider}. Set api_key in config.yaml or LLM_API_KEY env var")
    else:
        api_key = api_key or 'not-needed'
    
    # Provider-specific API handling
    if provider == 'anthropic':
        return _call_anthropic_api(prompt, base_url, model, api_key, max_tokens, temperature, top_p, top_k, min_p)
    elif provider == 'openrouter':
        return _call_openrouter_api(prompt, base_url, model, api_key, max_tokens, temperature, top_p, top_k, min_p)
    else:
        return _call_openai_compatible_api(prompt, base_url, model, api_key, max_tokens, temperature, top_p, top_k, min_p)


def _call_openai_compatible_api(prompt: str, base_url: str, model: str, api_key: str, max_tokens: int, temperature: float, top_p: float, top_k: int, min_p: float) -> str:
    """Call OpenAI-compatible API (used by OpenAI, LM Studio, Ollama)"""
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}]
        }
        
        # Only add optional parameters if configured
        if max_tokens is not None:
            data['max_tokens'] = max_tokens
        if temperature is not None:
            data['temperature'] = temperature
        if top_p is not None:
            data['top_p'] = top_p
        if top_k is not None:
            data['top_k'] = top_k
        if min_p is not None:
            data['min_p'] = min_p
        
        # Ensure base_url ends with /chat/completions
        if not base_url.endswith('/chat/completions'):
            if base_url.endswith('/v1'):
                api_url = f"{base_url}/chat/completions"
            else:
                api_url = f"{base_url}/v1/chat/completions"
        else:
            api_url = base_url
        
        logging.info(f"Making OpenAI-compatible API call to: {api_url}")
        
        response = requests.post(
            api_url,
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        if not content:
            logging.warning(f"Empty response from LLM. Full result: {result}")
            return "No response generated"
        
        logging.info(f"API call successful ({len(content)} chars)")
        
        # Clean thinking patterns from response
        cleaned_content = _remove_thinking_patterns(content)
        if len(cleaned_content) != len(content):
            logging.info(f"Removed thinking patterns ({len(content)} -> {len(cleaned_content)} chars)")
        
        return cleaned_content
        
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Connection failed to {api_url}. Is the server running?")
        raise
    except requests.exceptions.Timeout as e:
        logging.error(f"API call timed out. Local models may need more time.")
        raise
    except Exception as e:
        logging.error(f"API call failed: {e}")
        raise


def _call_openrouter_api(prompt: str, base_url: str, model: str, api_key: str, max_tokens: int, temperature: float, top_p: float, top_k: int, min_p: float) -> str:
    """Call OpenRouter API (OpenAI-compatible with extra headers)"""
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://github.com/zotero-llm-assistant',  # Required by OpenRouter
            'X-Title': 'Zotero LLM Assistant'  # Optional but nice
        }
        
        data = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}]
        }
        
        # Only add optional parameters if configured
        if max_tokens is not None:
            data['max_tokens'] = max_tokens
        if temperature is not None:
            data['temperature'] = temperature
        if top_p is not None:
            data['top_p'] = top_p
        if top_k is not None:
            data['top_k'] = top_k
        if min_p is not None:
            data['min_p'] = min_p
        
        api_url = f"{base_url}/chat/completions"
        logging.info(f"Making OpenRouter API call to: {api_url}")
        
        response = requests.post(
            api_url,
            headers=headers,
            json=data,
            timeout=120  # OpenRouter may need more time for some models
        )
        response.raise_for_status()
        
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        if not content:
            logging.warning(f"Empty response from OpenRouter. Full result: {result}")
            return "No response generated"
        
        logging.info(f"OpenRouter API call successful ({len(content)} chars)")
        
        # Clean thinking patterns from response
        cleaned_content = _remove_thinking_patterns(content)
        if len(cleaned_content) != len(content):
            logging.info(f"Removed thinking patterns ({len(content)} -> {len(cleaned_content)} chars)")
        
        return cleaned_content
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 402:
            logging.error("OpenRouter API call failed: Insufficient credits. Please check your OpenRouter account balance.")
        else:
            logging.error(f"OpenRouter API call failed with HTTP {e.response.status_code}: {e}")
        raise
    except Exception as e:
        logging.error(f"OpenRouter API call failed: {e}")
        raise


def _call_anthropic_api(prompt: str, base_url: str, model: str, api_key: str, max_tokens: int, temperature: float, top_p: float, top_k: int, min_p: float) -> str:
    """Call Anthropic Claude API (different format)"""
    try:
        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01'
        }
        
        data = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}]
        }
        
        # Only add optional parameters if configured
        if max_tokens is not None:
            data['max_tokens'] = max_tokens
        if temperature is not None:
            data['temperature'] = temperature
        if top_p is not None:
            data['top_p'] = top_p
        if top_k is not None:
            data['top_k'] = top_k
        # Note: Anthropic doesn't support min_p, so we skip it
        
        api_url = f"{base_url}/messages"
        logging.info(f"Making Anthropic API call to: {api_url}")
        
        response = requests.post(
            api_url,
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        content = result.get('content', [{}])[0].get('text', '')
        
        if not content:
            logging.warning(f"Empty response from Anthropic. Full result: {result}")
            return "No response generated"
        
        logging.info(f"Anthropic API call successful ({len(content)} chars)")
        
        # Clean thinking patterns from response
        cleaned_content = _remove_thinking_patterns(content)
        if len(cleaned_content) != len(content):
            logging.info(f"Removed thinking patterns ({len(content)} -> {len(cleaned_content)} chars)")
        
        return cleaned_content
        
    except Exception as e:
        logging.error(f"Anthropic API call failed: {e}")
        raise


def _remove_thinking_patterns(content: str) -> str:
    """
    Remove thinking patterns from LLM responses.
    Detects and removes common thinking model patterns like <thinking>, <thought>, etc.
    """
    import re
    
    # Common thinking patterns to remove
    patterns = [
        # XML-style thinking tags
        r'<thinking>.*?</thinking>',
        r'<thought>.*?</thought>',
        r'<think>.*?</think>',
        r'<reasoning>.*?</reasoning>',
        r'<analysis>.*?</analysis>',
        r'<consideration>.*?</consideration>',
        
        # Explicit thinking blocks
        r'\*\*Thinking:\*\*.*?(?=\n\n|\*\*[A-Z]|\n\*\*|$)',
        r'Thinking:.*?(?=\n\n|[A-Z][a-z]+:|$)',
        
        # QwQ-style thinking patterns
        r'<\|thinking\|>.*?<\|/thinking\|>',
        r'\[THINKING\].*?\[/THINKING\]',
        
        # o1-style patterns
        r'```thinking.*?```',
        r'<internal_thought>.*?</internal_thought>',
    ]
    
    cleaned = content
    
    # Apply each pattern with DOTALL flag to match across newlines
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    
    # Clean up extra whitespace and newlines
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)  # Multiple newlines to double
    cleaned = re.sub(r'^\s+', '', cleaned)  # Leading whitespace
    cleaned = re.sub(r'\s+$', '', cleaned)  # Trailing whitespace
    
    return cleaned.strip()



