"""
Tasks module for Zotero LLM Assistant

Core task implementations for analyzing and organizing Zotero items.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from . import main
from . import llm


def analyze_item(zot, item_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a Zotero item using LLM.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        config: Configuration dictionary
        
    Returns:
        Analysis results dictionary
    """
    try:
        # Get item metadata
        item = main.get_item_metadata(zot, item_id)
        item_data = item.get('data', {})
        
        title = item_data.get('title', 'Unknown Title')
        logging.info(f"Analyzing item: {title}")
        
        # Get fulltext if enabled
        fulltext = ""
        task_config = config.get('tasks', {}).get('analyze_item', {})
        
        if task_config.get('include_fulltext', True):
            fulltext_content = main.get_item_fulltext(zot, item_id)
            if fulltext_content:
                fulltext = fulltext_content
        
        # Call LLM for analysis
        analysis = _analyze_item_with_llm(item_data, fulltext, config)
        
        # Create note annotation with the analysis (if enabled)
        note_created = False
        if task_config.get('create_note', True):
            try:
                # Get model name from config
                model_name = config.get('llm', {}).get('model', 'Unknown Model')
                note_content = f"<pre>{analysis}</pre>"
                note_created = main.create_note_annotation(zot, item_id, note_content, model_name, "LLM Summary")
            except Exception as e:
                logging.warning(f"Failed to create note annotation: {e}")
        
        # Add llm_summary tag to the item (or parent if it's an attachment)
        tag_added = False
        if note_created:
            try:
                # Determine which item to tag (same logic as note creation)
                target_item_id = item_id
                
                # If this is an attachment, tag the parent item instead
                if item_data.get('itemType') == 'attachment':
                    parent_key = item_data.get('parentItem')
                    if parent_key:
                        target_item_id = parent_key
                        logging.info(f"Item {item_id} is an attachment, adding tag to parent {target_item_id}")
                
                # Add the tag
                tag_added = main.add_tag_to_item(zot, target_item_id, "llm_summary")
                if tag_added:
                    logging.info(f"Added 'llm_summary' tag to item {target_item_id}")
            except Exception as e:
                logging.warning(f"Failed to add llm_summary tag: {e}")
        
        result = {
            'item_id': item_id,
            'title': title,
            'analysis': analysis,
            'has_fulltext': bool(fulltext),
            'fulltext_length': len(fulltext) if fulltext else 0,
            'note_created': note_created,
            'tag_added': tag_added
        }
        
        logging.info(f"Analysis completed for item {item_id}")
        if note_created:
            logging.info(f"Summary saved as note annotation for item {item_id}")
        
        return result
        
    except Exception as e:
        logging.error(f"Failed to analyze item {item_id}: {e}")
        raise


def _analyze_item_with_llm(item_data: Dict[str, Any], fulltext: str, config: Dict[str, Any]) -> str:
    """
    Analyze a Zotero item using LLM.
    
    Args:
        item_data: Item metadata dictionary
        fulltext: Full text content
        config: Configuration dictionary
        
    Returns:
        LLM analysis response
    """
    # Load prompts configuration
    prompts_file = config.get('prompts_file', 'prompts.yaml')
    prompts_config = main.load_prompts(prompts_file)
    
    # Get task-specific prompt or use default
    task_prompt = prompts_config.get('tasks', {}).get('analyze_item', {}).get('prompt', '')
    if not task_prompt:
        raise ValueError("No prompt found for 'analyze_item' in the prompts configuration. Please check your prompts.yaml file.")
    
    # Extract relevant information from item data
    title = item_data.get('title', 'Unknown Title')
    authors = item_data.get('creators', [])
    author_names = [f"{c.get('firstName', '')} {c.get('lastName', '')}" for c in authors]
    abstract = item_data.get('abstractNote', '')
    
    # Prepare the full prompt
    content_prompt = f"""
{task_prompt}

Research Paper Details:
Title: {title}
Authors: {', '.join(author_names)}
Abstract: {abstract}

Full Text:
{fulltext}
"""
    
    # Check if the prompt exceeds the maximum length (if configured)
    task_config = config.get('tasks', {}).get('analyze_item', {})
    max_prompt_chars = task_config.get('max_prompt_chars')
    
    if max_prompt_chars is not None:
        if len(content_prompt) > max_prompt_chars:
            raise ValueError(
                f"Prompt too large ({len(content_prompt):,} characters). "
                f"Maximum allowed: {max_prompt_chars:,} characters. "
                f"Either increase max_prompt_chars in config or use a shorter document."
            )
    
    return llm.call_llm(content_prompt, config)


