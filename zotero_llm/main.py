"""
Zotero LLM Assistant - Core Module

This module provides core functionality for the Zotero LLM Assistant, including:
- Zotero Web API interactions using pyzotero
- LLM API calls for content analysis
- Item fulltext retrieval and processing
"""

import logging
import yaml
import requests
import os
from typing import Dict, Any, List, Optional
from pyzotero import zotero


def load_config(config_file='config.yaml') -> Dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logging.error(f"Config file {config_file} not found")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Error parsing config file: {e}")
        raise


def load_prompts(prompts_file='prompts.yaml') -> Dict[str, Any]:
    """Load prompts configuration from YAML file."""
    try:
        # Handle relative paths from the same directory as the script
        if not os.path.isabs(prompts_file):
            script_dir = os.path.dirname(os.path.dirname(__file__))
            prompts_file = os.path.join(script_dir, prompts_file)
            
        with open(prompts_file, 'r') as f:
            prompts = yaml.safe_load(f)
        return prompts
    except FileNotFoundError:
        logging.warning(f"Prompts file {prompts_file} not found, using default prompts")
        return {
            'system_prompt': 'You are an AI assistant specialized in analyzing research documents.',
            'tasks': {}
        }
    except yaml.YAMLError as e:
        logging.error(f"Error parsing prompts file: {e}")
        raise


def setup_logging(log_level='INFO'):
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def get_zotero_client(config: Dict[str, Any]) -> zotero.Zotero:
    """
    Create Zotero client using web API.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configured Zotero client instance
    """
    zotero_config = config.get('zotero', {})
    
    library_id = zotero_config.get('library_id')
    library_type = zotero_config.get('library_type', 'user')
    api_key = zotero_config.get('api_key')
    
    if not library_id or not api_key:
        raise ValueError(
            "Missing required Zotero credentials. Please set library_id and api_key in config.yaml"
        )
    
    try:
        client = zotero.Zotero(
            library_id=library_id,
            library_type=library_type,
            api_key=api_key,
            local=False  # Always use web API
        )
        
        logging.info(f"Connected to Zotero Web API (library: {library_id}, type: {library_type})")
        return client
        
    except Exception as e:
        logging.error(f"Failed to connect to Zotero Web API: {e}")
        raise


def get_item_metadata(zot: zotero.Zotero, item_id: str) -> Dict[str, Any]:
    """
    Get detailed metadata for a specific item.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        
    Returns:
        Item metadata dictionary
    """
    try:
        item = zot.item(item_id)
        logging.info(f"Retrieved metadata for item {item_id}")
        return item
    except Exception as e:
        logging.error(f"Failed to get metadata for item {item_id}: {e}")
        raise


def get_item_fulltext(zot: zotero.Zotero, item_id: str) -> Optional[str]:
    """
    Get full text content for a Zotero item using web API.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        
    Returns:
        Full text content or None if not available
    """
    try:
        logging.info(f"Getting fulltext for item {item_id}")
        
        # Get item metadata first
        item = zot.item(item_id)
        item_type = item.get('data', {}).get('itemType')
        
        # If this is an attachment, try fulltext directly
        if item_type == 'attachment':
            try:
                fulltext_result = zot.fulltext_item(item_id)
                if fulltext_result and 'content' in fulltext_result:
                    content = fulltext_result['content']
                    logging.info(f"Retrieved fulltext from attachment {item_id} ({len(content)} chars)")
                    return content
            except Exception as e:
                logging.warning(f"Failed to get fulltext for attachment {item_id}: {e}")
                return None
        
        # For regular items, look for PDF attachments
        try:
            children = zot.children(item_id)
            pdf_attachments = [
                child for child in children 
                if child.get('data', {}).get('itemType') == 'attachment' and
                child.get('data', {}).get('contentType') == 'application/pdf'
            ]
            
            if not pdf_attachments:
                logging.warning(f"No PDF attachments found for item {item_id}")
                return None

            # Try to get fulltext from the first PDF attachment
            for attachment in pdf_attachments:
                attachment_id = attachment.get('key')
                try:
                    fulltext_result = zot.fulltext_item(attachment_id)
                    if fulltext_result and 'content' in fulltext_result:
                        content = fulltext_result['content']
                        logging.info(f"Retrieved fulltext from attachment {attachment_id} ({len(content)} chars)")
                        return content
                except Exception as e:
                    logging.warning(f"Failed to get fulltext for attachment {attachment_id}: {e}")
                    continue
                    
            logging.warning(f"No fulltext content available for item {item_id}")
            return None
            
        except Exception as e:
            logging.error(f"Failed to get children for item {item_id}: {e}")
            return None
            
    except Exception as e:
        logging.error(f"Failed to get fulltext for item {item_id}: {e}")
        return None


def search_items(zot: zotero.Zotero, query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Search for items in Zotero library.
    
    Args:
        zot: Zotero client instance
        query: Search query string
        limit: Maximum number of results
        
    Returns:
        List of item dictionaries
    """
    try:
        logging.info(f"Searching for items with query: '{query}'")
        
        # Use pyzotero's search functionality
        zot.add_parameters(q=query, limit=limit, itemType='-attachment')
        results = zot.items()
        
        logging.info(f"Found {len(results)} items")
        return results
                
    except Exception as e:
        logging.error(f"Search failed: {e}")
        raise


def get_collections(zot: zotero.Zotero) -> List[Dict[str, Any]]:
    """
    Get all collections from the library.
    
    Args:
        zot: Zotero client instance
        
    Returns:
        List of collection dictionaries
    """
    try:
        collections = zot.collections()
        logging.info(f"Retrieved {len(collections)} collections")
        return collections
    except Exception as e:
        logging.error(f"Failed to get collections: {e}")
        raise


def create_note_annotation(zot: zotero.Zotero, item_id: str, content: str, model_name: str = "LLM", title: str = "LLM Summary") -> bool:
    """
    Create a note annotation for a Zotero item.
    If the item is an attachment, the note will be attached to its parent item.
    If a note with the same title exists, adds a number suffix.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        content: Content of the note
        model_name: Name of the model used for analysis
        title: Base title of the note (optional)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the item to check if it's an attachment
        item = zot.item(item_id)
        
        # If this is an attachment, find its parent item
        parent_item_id = item_id
        if item['data'].get('itemType') == 'attachment':
            parent_key = item['data'].get('parentItem')
            if parent_key:
                parent_item_id = parent_key
                logging.info(f"Item {item_id} is an attachment, attaching note to parent {parent_item_id}")
            else:
                logging.warning(f"Attachment {item_id} has no parent item, creating standalone note")
                parent_item_id = None  # Create standalone note
        
        # Check for existing notes to avoid duplicates
        unique_title = title
        if parent_item_id:
            # Get existing child notes
            try:
                existing_items = zot.children(parent_item_id)
                existing_notes = [item for item in existing_items if item['data'].get('itemType') == 'note']
                existing_titles = [note['data'].get('note', '')[:50] for note in existing_notes]  # First 50 chars as title proxy
                
                # Find a unique title
                counter = 1
                base_content_start = f"<h2>{title}</h2>"
                while any(base_content_start in existing_title for existing_title in existing_titles):
                    unique_title = f"{title} ({counter})"
                    base_content_start = f"<h2>{unique_title}</h2>"
                    counter += 1
                    
            except Exception as e:
                logging.warning(f"Could not check existing notes: {e}")
        
        # Format content with model info
        formatted_content = f"<h2>{unique_title}</h2><p><strong>Model:</strong> {model_name}</p>{content}"
        
        # Prepare note data
        note_data = {
            "itemType": "note",
            "note": formatted_content
        }
        
        # Add parent item if we have one
        if parent_item_id:
            note_data["parentItem"] = parent_item_id
        
        # Create the note
        result = zot.create_items([note_data])
        
        if result and "success" in result and result["success"]:
            note_key = next(iter(result["success"].keys()))
            note_type = "attached" if parent_item_id else "standalone"
            logging.info(f"Created {note_type} summary note '{unique_title}' (note key: {note_key}) for item {item_id}")
            return True
        else:
            logging.error(f"Failed to create note for item {item_id}: {result}")
            return False
            
    except Exception as e:
        logging.error(f"Error creating note for item {item_id}: {e}")
        return False


def add_tag_to_item(zot: zotero.Zotero, item_id: str, tag: str) -> bool:
    """
    Add a tag to a Zotero item.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        tag: Tag string to add
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current item
        item = zot.item(item_id)
        
        # Get existing tags
        existing_tags = item['data'].get('tags', [])
        tag_names = [t.get('tag') for t in existing_tags]
        
        # Check if tag already exists
        if tag in tag_names:
            logging.info(f"Tag '{tag}' already exists on item {item_id}")
            return True
        
        # Add the new tag
        existing_tags.append({'tag': tag})
        item['data']['tags'] = existing_tags
        
        # Save changes
        result = zot.update_item(item)
        
        if result:
            logging.info(f"Added tag '{tag}' to item {item_id}")
            return True
        else:
            logging.error(f"Failed to add tag '{tag}' to item {item_id}")
            return False
            
    except Exception as e:
        logging.error(f"Error adding tag '{tag}' to item {item_id}: {e}")
        return False


def find_collection_by_path(zot: zotero.Zotero, collection_path: str) -> Optional[str]:
    """
    Find a collection by its hierarchical path (e.g., 'a/b/c').
    
    Args:
        zot: Zotero client instance
        collection_path: Slash-separated path to the collection
        
    Returns:
        Collection key if found, None otherwise
    """
    try:
        # Split the path into components
        path_parts = [part.strip() for part in collection_path.strip('/').split('/') if part.strip()]
        
        if not path_parts:
            raise ValueError("Empty collection path provided")
        
        # Get all collections
        all_collections = zot.collections()
        
        # Create a mapping of collection key to collection data
        collections_by_key = {col['key']: col for col in all_collections}
        
        # Start with top-level collections (no parentCollection)
        current_collections = [col for col in all_collections if not col['data'].get('parentCollection')]
        
        # Navigate through the path
        for i, part in enumerate(path_parts):
            # Find collection with matching name at current level
            found_collection = None
            for col in current_collections:
                if col['data'].get('name', '').lower() == part.lower():
                    found_collection = col
                    break
            
            if not found_collection:
                logging.error(f"Collection '{part}' not found at path level {i + 1} in '{collection_path}'")
                return None
            
            # If this is the last part, return the collection key
            if i == len(path_parts) - 1:
                logging.info(f"Found collection '{found_collection['data']['name']}' with key {found_collection['key']}")
                return found_collection['key']
            
            # Otherwise, get subcollections for next iteration
            collection_key = found_collection['key']
            current_collections = [
                col for col in all_collections 
                if col['data'].get('parentCollection') == collection_key
            ]
            
            if not current_collections:
                logging.error(f"No subcollections found under '{part}' at path '{collection_path}'")
                return None
        
        return None
        
    except Exception as e:
        logging.error(f"Error finding collection by path '{collection_path}': {e}")
        return None


def has_llm_summary_tag(item: Dict[str, Any]) -> bool:
    """
    Check if an item has the llm_summary tag.
    
    Args:
        item: Item metadata dictionary
        
    Returns:
        True if item has llm_summary tag, False otherwise
    """
    tags = item.get('data', {}).get('tags', [])
    tag_names = [tag.get('tag', '').lower() for tag in tags]
    return 'llm_summary' in tag_names


def get_collection_items(zot: zotero.Zotero, collection_key: str, recursive: bool = False) -> List[Dict[str, Any]]:
    """
    Get all items from a collection, optionally including subcollections.
    
    Args:
        zot: Zotero client instance
        collection_key: Zotero collection key
        recursive: If True, include items from subcollections
        
    Returns:
        List of item dictionaries (excluding attachments)
    """
    try:
        # Get items directly in this collection
        items = zot.collection_items(collection_key)
        
        # Filter out attachments to get only main items
        main_items = [item for item in items if item['data'].get('itemType') != 'attachment']
        
        logging.info(f"Found {len(main_items)} main items in collection {collection_key}")
        
        if recursive:
            # Get all collections to find subcollections
            all_collections = zot.collections()
            subcollections = [
                col for col in all_collections 
                if col['data'].get('parentCollection') == collection_key
            ]
            
            # Recursively get items from subcollections
            for subcol in subcollections:
                subcol_key = subcol['key']
                subcol_name = subcol['data'].get('name', 'Unknown')
                logging.info(f"Processing subcollection: {subcol_name}")
                
                subcol_items = get_collection_items(zot, subcol_key, recursive=True)
                main_items.extend(subcol_items)
        
        return main_items
        
    except Exception as e:
        logging.error(f"Failed to get items from collection {collection_key}: {e}")
        raise



