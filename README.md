# Zotero LLM Assistant

A simple, clean tool for analyzing and organizing your Zotero research library using local and remote Large Language Models.

**Important**: by default, this tool uses full text analysis. Please make sure you are using a model with enough context length, and that you understand the potential costs if using a remote provider. Open-weights SOTA models from OpenRouter are recommended due to being significantly cheaper than OpenAI or Anthropic.

## Tasks

- **LLM Summary** (`llm_summary`): Uses Zotero's web API to analyze a paper and write the summary to a note attached to the item. Adds a "llm_summary" tag to the item. Works on both individual items and entire collections.

- **Key References** (`key_references`): Extracts the most important and influential references from a research paper and writes them to a "Key References" note. Adds a "key_references" tag to the item. Works on both individual items and entire collections.

- **Missing PDF** (`missing_pdf`): Database-level task that flags all items without PDF attachments by adding a "missing_pdf" tag. Also removes the flag from items that now have PDFs. Prints the names and collection paths of affected items.

- **Summary Q&A** (`summary_qa`): Collection-level task that uses existing LLM summaries and optionally key references from all items in a collection to answer free-form questions. Creates a note in a dedicated "#LLM QA" collection structure (created automatically) with the question and answer. Notes are organized into subcollections based on the top-level collection of the source (e.g., notes from "Complex Networks/Scaling laws" go into "#LLM QA/Complex Networks"). All QA notes receive an "llm_qa" tag for easy filtering. Requires items to have been previously processed with `llm_summary` task. This task automatically uses extended timeouts due to the complexity of multi-paper analysis.

The analysis tasks automatically skip items with existing tags to prevent duplicates and require fulltext (PDFs) by default.

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
     provider: "local"        # Options: local, openai, anthropic, openrouter
     model: "local-model"     # Model name (REQUIRED)
     port: 1234               # Port for local provider (REQUIRED - 1234=LM Studio, 11434=Ollama)
     api_key: null            # Only needed for remote providers
     timeout: 60              # Optional: API timeout in seconds (default: 60s for most, 120s for OpenRouter)
   ```

3. **Start your LLM server** (for local provider):
   - **LM Studio**: Start server on port 1234
   - **Ollama**: `ollama serve` (uses port 11434)
   - **Other local servers**: Use any port, just set it in `config.yaml`

4. **Process an item**:
   ```bash
   # Generate LLM summary for an item
   python run_assistant.py llm_summary item --item-id ITEM_KEY
   
   # Extract key references from an item
   python run_assistant.py key_references item --item-id ITEM_KEY
   ```

5. **Process a collection**:
   ```bash
   # Generate LLM summaries for all items in a collection
   python run_assistant.py llm_summary collection --collection-path "folder/subfolder"
   
   # Extract key references for all items in a collection
   python run_assistant.py key_references collection --collection-path "folder/subfolder"
   
   # Process multiple collections at once
   python run_assistant.py llm_summary collection --collection-path "Research/AI Papers" "Research/ML Theory" "Papers/NLP"
   
   # Process all unfiled items (items not in any collection)
   python run_assistant.py llm_summary collection --unfiled
   ```

6. **Database-level tasks**:
   ```bash
   # Flag all items missing PDF attachments
   python run_assistant.py missing_pdf
   ```

   **Pro tip**: By default, items already processed (with task-specific tags) are skipped. Use `--no-skip-analyzed` to force re-processing of all items.

## Command Line Options

### Command Structure
```bash
python run_assistant.py [OPTIONS] TASK [OBJECT_TYPE] [TASK_OPTIONS]
```

**Object Types:**
- `item` - Process a single item
- `collection` - Process all items in a collection

**Tasks:**
- `llm_summary` - Generate LLM analysis summary (requires object type)
- `key_references` - Extract key references from paper (requires object type)  
- `missing_pdf` - Flag items missing PDF attachments (database-level)
- `summary_qa` - Answer questions using collection summaries (collection-level only)

### Common Flags
- `-c, --config`: Configuration file path (default: `config.yaml`)
- `--skip-analyzed`: Skip items already processed (default: `true`)
- `--no-skip-analyzed`: Force re-processing of all items, even those already processed
- `--verbose`: Enable debug logging
- `--log-level`: Set logging level (DEBUG, INFO, WARNING, ERROR)

### Task Options
- `--item-id ITEM_ID`: Specific Zotero item ID to process
- `--query "search term"`: Search for item by title/content
- `--collection-path "path1" "path2" ...`: One or more hierarchical collection paths (supports subcollections)
- `--unfiled`: Process all unfiled items (items not assigned to any collection)
- `--all-collections`: Process all collections in the library (collection-level tasks only)
- `--question "question"`: Question to ask when using summary_qa task
- `--references`: Include Key References with summaries in summary_qa (default: true)
- `--no-references`: Do not include Key References with summaries in summary_qa

### Examples
```bash
# Generate LLM summaries for collection, skipping already processed items (default)
python run_assistant.py llm_summary collection --collection-path "Research/AI Papers"

# Extract key references for all items in collection
python run_assistant.py key_references collection --collection-path "Research/AI Papers"

# Process multiple collections at once
python run_assistant.py llm_summary collection --collection-path "Research/AI Papers" "Research/ML Theory" "Papers/NLP"

# Force re-processing of all items in multiple collections
python run_assistant.py llm_summary collection --collection-path "Research/AI Papers" "Research/ML Theory" --no-skip-analyzed

# Process all unfiled items (items not in any collection)
python run_assistant.py llm_summary collection --unfiled

# Process ALL collections in the library
python run_assistant.py llm_summary collection --all-collections

# Extract key references from unfiled items only
python run_assistant.py key_references collection --unfiled

# Extract key references from ALL collections
python run_assistant.py key_references collection --all-collections

# Process single item by search query
python run_assistant.py llm_summary item --query "attention mechanism"

# Use custom config file
python run_assistant.py -c my_config.yaml key_references item --item-id ABC123

# Enable verbose logging
python run_assistant.py --verbose llm_summary collection --collection-path "Research"

# Process items without PDFs using metadata only
python run_assistant.py llm_summary item --item-id ABC123
# (Set include_fulltext: false in config.yaml for metadata-only analysis)

# Database-level task: flag items missing PDFs
python run_assistant.py missing_pdf

# Answer questions using collection summaries (creates a note in "#LLM QA/[TopLevelCollection]" subcollection)
python run_assistant.py summary_qa collection --collection-path "Research/AI Papers" --question "What are the main limitations discussed in these papers?"

# Answer questions without including key references (creates a note in "#LLM QA/[TopLevelCollection]" subcollection)
python run_assistant.py summary_qa collection --collection-path "Research/NLP" --question "What methods are most commonly used?" --no-references
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
- **OpenRouter**: `openrouter` (access to 100+ models from different providers)

#### Local Provider
For the local provider, you must specify the port in `config.yaml`. Common ports:
- LM Studio: 1234
- Ollama: 11434
- Custom: any port your local server uses

#### Remote Providers
For remote providers, set your API key in `config.yaml` or use the `LLM_API_KEY` environment variable.

**OpenAI Example:**
```yaml
llm:
  provider: "openai"
  model: "gpt-4o"
  api_key: "sk-..."
  temperature: 0.7
```

**Anthropic Example:**
```yaml
llm:
  provider: "anthropic" 
  model: "claude-3-5-sonnet-20241022"
  api_key: "sk-ant-..."
  temperature: 0.7
```

**OpenRouter Example:**
```yaml
llm:
  provider: "openrouter"
  model: "anthropic/claude-3.5-sonnet"  # or "openai/gpt-4o", "meta-llama/llama-3.1-405b", etc.
  api_key: "sk-or-..."
  temperature: 0.7
```

#### Getting API Keys
- **OpenAI**: Get your API key at https://platform.openai.com/api-keys
- **Anthropic**: Get your API key at https://console.anthropic.com/
- **OpenRouter**: Get your API key at https://openrouter.ai/keys (supports 100+ models from multiple providers)