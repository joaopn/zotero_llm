# Zotero LLM Assistant

A simple, clean tool for analyzing and organizing your Zotero research library using Large Language Models.

## Tasks

- **Paper analyzer**: Uses Zotero's web API to analyze a paper (from its ID) and write the result to a note (`analyze_item`)

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your provider** in `config.yaml`:
   ```yaml
   zotero:
     library_id: "YOUR_LIBRARY_ID"
     api_key: "YOUR_API_KEY"
   
   llm:
     provider: "lm_studio"    # Options: lm_studio, ollama, openai, anthropic
     model: "local-model"     # Model name (REQUIRED)
     api_key: null            # Only needed for openai/anthropic
   ```

3. **Start your LLM server** (for local providers):
   - **LM Studio**: Start server on port 1234
   - **Ollama**: `ollama serve` (uses port 11434)

4. **Analyze an item**:
   ```bash
   python run_assistant.py --task analyze_item --item-id ITEM_KEY
   ```

## Credentials

### Zotero API
1. Go to https://www.zotero.org/settings/keys
2. Create a new private key with read and write access
3. Your library ID is in your Zotero URL: `zotero.org/users/YOUR_ID`

### LLM Provider Setup

Currently supported providers are

- LM Studio: `lm_studio` (local)
- Ollama: `ollama` (local)
- OpenAI: `openai`
- Anthropic: `anthropic`

For the local providers, their default ports are hardcoded and `api_key` is `null`.