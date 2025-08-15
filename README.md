# Zotero LLM Assistant

A simple, clean tool for analyzing and organizing your Zotero research library using local and remote Large Language Models.

## Tasks

- **Paper analyzer** (`analyze_item`): Uses Zotero's web API to analyze a paper (using its ID) and write the summary to a note attached to the item. Adds a "llm_summary" tag to the item.

- **Collection analyzer** (`analyze_collection`): Analyzes all parent items in a collection and its subcollections. Uses the same analysis as `analyze_item` but processes multiple documents at once. Supports hierarchical collection paths (e.g., `folder/subfolder`). Automatically skips items with existing `llm_summary` tags to prevent duplicates.

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
     provider: "local"        # Options: local, openai, anthropic
     model: "local-model"     # Model name (REQUIRED)
     port: 1234               # Port for local provider (REQUIRED - 1234=LM Studio, 11434=Ollama)
     api_key: null            # Only needed for openai/anthropic
   ```

3. **Start your LLM server** (for local provider):
   - **LM Studio**: Start server on port 1234
   - **Ollama**: `ollama serve` (uses port 11434)
   - **Other local servers**: Use any port, just set it in `config.yaml`

4. **Analyze an item**:
   ```bash
   python run_assistant.py analyze_item --item-id ITEM_KEY
   ```

5. **Analyze a collection**:
   ```bash
   python run_assistant.py analyze_collection --collection-path "folder/subfolder"
   ```

   **Pro tip**: By default, items already analyzed (with `llm_summary` tag) are skipped. Use `--no-skip-analyzed` to force re-analysis of all items.

## Command Line Options

### Common Flags
- `-c, --config`: Configuration file path (default: `config.yaml`)
- `--skip-analyzed`: Skip items already analyzed (default: `true`)
- `--no-skip-analyzed`: Force re-analysis of all items, even those already processed
- `--verbose`: Enable debug logging
- `--log-level`: Set logging level (DEBUG, INFO, WARNING, ERROR)

### Examples
```bash
# Analyze collection, skipping already processed items (default)
python run_assistant.py analyze_collection --collection-path "Research/AI Papers"

# Force re-analysis of all items in collection
python run_assistant.py analyze_collection --collection-path "Research/AI Papers" --no-skip-analyzed

# Use custom config file
python run_assistant.py -c my_config.yaml analyze_item --item-id ABC123

# Enable verbose logging
python run_assistant.py --verbose analyze_collection --collection-path "Research"
```

## Credentials

### Zotero API
1. Go to https://www.zotero.org/settings/keys
2. Create a new private key with read and write access
3. Your library ID is in your Zotero URL: `zotero.org/users/YOUR_ID`

### LLM Provider Setup

Currently supported providers are:

- **Local**: `local` (configurable port - supports LM Studio, Ollama, or any OpenAI-compatible local server)
- **OpenAI**: `openai`
- **Anthropic**: `anthropic`

For the local provider, you must specify the port in `config.yaml`. Common ports:
- LM Studio: 1234
- Ollama: 11434
- Custom: any port your local server uses