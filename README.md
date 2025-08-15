# Zotero LLM Assistant

A simple, clean tool for analyzing and organizing your Zotero research library using local and remote Large Language Models.

## Tasks

- **LLM Summary** (`llm_summary`): Uses Zotero's web API to analyze a paper and write the summary to a note attached to the item. Adds a "llm_summary" tag to the item. Works on both individual items and entire collections.

- **Key References** (`key_references`): Extracts the most important and influential references from a research paper and writes them to a "Key References" note. Adds a "key_references" tag to the item. Works on both individual items and entire collections.

Both tasks automatically skip items with existing tags to prevent duplicates and require fulltext (PDFs) by default.

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

4. **Process an item**:
   ```bash
   # Generate LLM summary for an item
   python run_assistant.py item llm_summary --item-id ITEM_KEY
   
   # Extract key references from an item
   python run_assistant.py item key_references --item-id ITEM_KEY
   ```

5. **Process a collection**:
   ```bash
   # Generate LLM summaries for all items in a collection
   python run_assistant.py collection llm_summary --collection-path "folder/subfolder"
   
   # Extract key references for all items in a collection
   python run_assistant.py collection key_references --collection-path "folder/subfolder"
   ```

   **Pro tip**: By default, items already processed (with task-specific tags) are skipped. Use `--no-skip-analyzed` to force re-processing of all items.

## Command Line Options

### Command Structure
```bash
python run_assistant.py [OPTIONS] OBJECT_TYPE TASK [TASK_OPTIONS]
```

**Object Types:**
- `item` - Process a single item
- `collection` - Process all items in a collection

**Tasks:**
- `llm_summary` - Generate LLM analysis summary
- `key_references` - Extract key references from paper

### Common Flags
- `-c, --config`: Configuration file path (default: `config.yaml`)
- `--skip-analyzed`: Skip items already processed (default: `true`)
- `--no-skip-analyzed`: Force re-processing of all items, even those already processed
- `--verbose`: Enable debug logging
- `--log-level`: Set logging level (DEBUG, INFO, WARNING, ERROR)

### Task Options
- `--item-id ITEM_ID`: Specific Zotero item ID to process
- `--query "search term"`: Search for item by title/content
- `--collection-path "path/to/collection"`: Hierarchical collection path

### Examples
```bash
# Generate LLM summaries for collection, skipping already processed items (default)
python run_assistant.py collection llm_summary --collection-path "Research/AI Papers"

# Extract key references for all items in collection
python run_assistant.py collection key_references --collection-path "Research/AI Papers"

# Force re-processing of all items in collection
python run_assistant.py collection llm_summary --collection-path "Research/AI Papers" --no-skip-analyzed

# Process single item by search query
python run_assistant.py item llm_summary --query "attention mechanism"

# Use custom config file
python run_assistant.py -c my_config.yaml item key_references --item-id ABC123

# Enable verbose logging
python run_assistant.py --verbose collection llm_summary --collection-path "Research"

# Process items without PDFs using metadata only
python run_assistant.py item llm_summary --item-id ABC123
# (Set include_fulltext: false in config.yaml for metadata-only analysis)
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