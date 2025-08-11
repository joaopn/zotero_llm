"""
Tasks module for Zotero LLM Assistant

Core task implementations for analyzing and organizing Zotero items.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from . import main
from . import llm


def analyze_item(zot, item_id: str, config: Dict[str, Any], skip_analyzed: bool = False) -> Dict[str, Any]:
    """
    Analyze a Zotero item using LLM.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        config: Configuration dictionary
        skip_analyzed: If True, skip items that already have llm_summary tag
        
    Returns:
        Analysis results dictionary
    """
    try:
        # Get item metadata first
        item = main.get_item_metadata(zot, item_id)
        item_data = item.get('data', {})
        
        title = item_data.get('title', 'Unknown Title')
        
        # Check if item is already analyzed and should be skipped BEFORE doing any work
        if skip_analyzed:
            # For attachments, we need to check the parent item for the tag
            target_item_for_tag_check = item
            if item_data.get('itemType') == 'attachment':
                parent_key = item_data.get('parentItem')
                if parent_key:
                    # Get parent item to check for tag
                    parent_item = main.get_item_metadata(zot, parent_key)
                    target_item_for_tag_check = parent_item
                    logging.info(f"Item {item_id} is an attachment, checking parent {parent_key} for llm_summary tag")
            
            if main.has_llm_summary_tag(target_item_for_tag_check):
                logging.info(f"Skipping already analyzed item: {title}")
                return {
                    'item_id': item_id,
                    'title': title,
                    'analysis': None,
                    'has_fulltext': False,
                    'fulltext_length': 0,
                    'note_created': False,
                    'tag_added': False,
                    'skipped': True,
                    'skip_reason': 'Already analyzed (has llm_summary tag)'
                }
        
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
            'tag_added': tag_added,
            'skipped': False
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


def analyze_collection(zot, collection_path: str, config: Dict[str, Any], skip_analyzed: bool = False) -> Dict[str, Any]:
    """
    Analyze all items in a Zotero collection and its subcollections using LLM.
    
    Args:
        zot: Zotero client instance
        collection_path: Slash-separated path to the collection (e.g., 'a/b/c')
        config: Configuration dictionary
        skip_analyzed: If True, skip items that already have llm_summary tag
        
    Returns:
        Analysis results dictionary
    """
    try:
        # Find the collection by path
        collection_key = main.find_collection_by_path(zot, collection_path)
        if not collection_key:
            raise ValueError(f"Collection not found at path: {collection_path}")
        
        # Get all items from the collection and its subcollections
        items = main.get_collection_items(zot, collection_key, recursive=True)
        
        if not items:
            logging.warning(f"No items found in collection at path: {collection_path}")
            return {
                'collection_path': collection_path,
                'collection_key': collection_key,
                'total_items': 0,
                'analyzed_items': 0,
                'successful_analyses': 0,
                'failed_analyses': 0,
                'skipped_analyses': 0,
                'results': []
            }
        
        logging.info(f"Found {len(items)} items to analyze in collection: {collection_path}")
        
        # Analyze each item
        results = []
        successful_analyses = 0
        failed_analyses = 0
        skipped_analyses = 0
        
        for i, item in enumerate(items, 1):
            item_id = item.get('key')
            title = item.get('data', {}).get('title', 'Unknown Title')
            
            logging.info(f"Processing item {i}/{len(items)}: {title}")
            
            try:
                # Use the existing analyze_item function
                result = analyze_item(zot, item_id, config, skip_analyzed)
                results.append(result)
                
                if result.get('skipped', False):
                    skipped_analyses += 1
                    logging.info(f"Skipped item {i}/{len(items)}: {title}")
                else:
                    successful_analyses += 1
                    logging.info(f"Successfully analyzed item {i}/{len(items)}: {title}")
                
            except Exception as e:
                logging.error(f"Failed to analyze item {i}/{len(items)} ({title}): {e}")
                failed_analyses += 1
                results.append({
                    'item_id': item_id,
                    'title': title,
                    'error': str(e),
                    'analysis': None,
                    'has_fulltext': False,
                    'fulltext_length': 0,
                    'note_created': False,
                    'tag_added': False,
                    'skipped': False
                })
        
        collection_result = {
            'collection_path': collection_path,
            'collection_key': collection_key,
            'total_items': len(items),
            'analyzed_items': len(results),
            'successful_analyses': successful_analyses,
            'failed_analyses': failed_analyses,
            'skipped_analyses': skipped_analyses,
            'results': results
        }
        
        logging.info(f"Collection analysis completed: {successful_analyses}/{len(items)} items successfully analyzed, {skipped_analyses} skipped")
        
        return collection_result
        
    except Exception as e:
        logging.error(f"Failed to analyze collection at path '{collection_path}': {e}")
        raise


