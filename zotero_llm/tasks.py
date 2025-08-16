"""
Tasks module for Zotero LLM Assistant

Core task implementations for analyzing and organizing Zotero items.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from . import main
from . import llm


def analyze_item(zot, item_id: str, config: Dict[str, Any], skip_analyzed: bool = False, task_name: str = 'llm_summary') -> Dict[str, Any]:
    """
    Analyze a Zotero item using LLM with configurable task.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        config: Configuration dictionary
        skip_analyzed: If True, skip items that already have the task tag
        task_name: Name of the task (analyze_item, key_references, etc.)
        
    Returns:
        Analysis results dictionary
    """
    # Task configuration mapping
    TASK_CONFIGS = {
        'llm_summary': {
            'prompt': 'analyze_item',
            'note_name': 'LLM Summary',
            'tag': 'llm_summary'
        },
        'key_references': {
            'prompt': 'key_references', 
            'note_name': 'Key References',
            'tag': 'key_references'
        }
    }
    
    # Validate task name
    if task_name not in TASK_CONFIGS:
        raise ValueError(f"Unknown task: {task_name}. Available tasks: {list(TASK_CONFIGS.keys())}")
    
    task_config = TASK_CONFIGS[task_name]
    
    try:
        # Get item metadata first
        item = main.get_item_metadata(zot, item_id)
        item_data = item.get('data', {})
        
        title = item_data.get('title', 'Unknown Title')
        
        # Check if item is already processed and should be skipped BEFORE doing any work
        tag_name = task_config['tag']
        
        if skip_analyzed:
            # For attachments, we need to check the parent item for the tag
            target_item_for_tag_check = item
            if item_data.get('itemType') == 'attachment':
                parent_key = item_data.get('parentItem')
                if parent_key:
                    # Get parent item to check for tag
                    parent_item = main.get_item_metadata(zot, parent_key)
                    target_item_for_tag_check = parent_item
                    logging.info(f"Item {item_id} is an attachment, checking parent {parent_key} for {tag_name} tag")
            
            # Check for task-specific tag
            tags = target_item_for_tag_check.get('data', {}).get('tags', [])
            tag_names = [tag.get('tag', '').lower() for tag in tags]
            if tag_name in tag_names:
                logging.info(f"Skipping already processed item: {title}")
                return {
                    'item_id': item_id,
                    'title': title,
                    'analysis': None,
                    'has_fulltext': False,
                    'fulltext_length': 0,
                    'note_created': False,
                    'tag_added': False,
                    'skipped': True,
                    'skip_reason': f'Already processed (has {tag_name} tag)'
                }
        
        action = "Analyzing" if task_name == 'llm_summary' else f"Processing ({task_name})"
        logging.info(f"{action} item: {title}")
        
        # Get fulltext - required for analysis
        config_section = config.get('tasks', {}).get(task_name, {})
        
        fulltext = ""
        if config_section.get('include_fulltext', True):
            fulltext_content = main.get_item_fulltext(zot, item_id)
            if fulltext_content:
                fulltext = fulltext_content
            else:
                # No fulltext available - skip this item
                logging.info(f"Skipping item {title} - no fulltext available")
                return {
                    'item_id': item_id,
                    'title': title,
                    'analysis': None,
                    'has_fulltext': False,
                    'fulltext_length': 0,
                    'note_created': False,
                    'tag_added': False,
                    'skipped': True,
                    'skip_reason': 'No fulltext available'
                }
        
        # Call LLM for analysis/processing
        analysis = _analyze_item_with_llm(item_data, fulltext, config, task_config['prompt'])
        
        # Create note annotation with the analysis (if enabled)
        note_title = task_config['note_name']
        note_created = False
        if config_section.get('create_note', True):
            try:
                # Get model name from config
                model_name = config.get('llm', {}).get('model', 'Unknown Model')
                note_content = f"<pre>{analysis}</pre>"
                note_created = main.create_note_annotation(zot, item_id, note_content, model_name, note_title)
            except Exception as e:
                logging.warning(f"Failed to create note annotation: {e}")
        
        # Add task-specific tag to the item (or parent if it's an attachment)
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
                tag_added = main.add_tag_to_item(zot, target_item_id, tag_name)
                if tag_added:
                    logging.info(f"Added '{tag_name}' tag to item {target_item_id}")
            except Exception as e:
                logging.warning(f"Failed to add {tag_name} tag: {e}")
        
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
        
        logging.info(f"{task_name} completed for item {item_id}")
        if note_created:
            logging.info(f"{note_title} saved as note annotation for item {item_id}")
        
        return result
        
    except Exception as e:
        logging.error(f"Failed to analyze item {item_id}: {e}")
        raise


def _analyze_item_with_llm(item_data: Dict[str, Any], fulltext: str, config: Dict[str, Any], prompt_name: str = 'analyze_item') -> str:
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
    task_prompt = prompts_config.get('tasks', {}).get(prompt_name, {}).get('prompt', '')
    if not task_prompt:
        raise ValueError(f"No prompt found for '{prompt_name}' in the prompts configuration. Please check your prompts.yaml file.")
    
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
    # Note: We use prompt_name here to look up config since it matches the task section
    config_section = config.get('tasks', {}).get(prompt_name, {})
    max_prompt_chars = config_section.get('max_prompt_chars')
    
    if max_prompt_chars is not None:
        if len(content_prompt) > max_prompt_chars:
            raise ValueError(
                f"Prompt too large ({len(content_prompt):,} characters). "
                f"Maximum allowed: {max_prompt_chars:,} characters. "
                f"Either increase max_prompt_chars in config or use a shorter document."
            )
    
    return llm.call_llm(content_prompt, config)


def _analyze_items_list(zot, items: List[Dict[str, Any]], config: Dict[str, Any], skip_analyzed: bool, task_name: str, collection_name: str, collection_key: str = None) -> Dict[str, Any]:
    """
    Analyze a list of items using LLM (shared logic for collections and unfiled items).
    
    Args:
        zot: Zotero client instance
        items: List of item dictionaries to analyze
        config: Configuration dictionary
        skip_analyzed: If True, skip items that already have task-specific tags
        task_name: Name of the task to perform
        collection_name: Display name for logging/results (e.g., "Collection Name" or "Unfiled Items")
        collection_key: Collection key (None for unfiled items)
        
    Returns:
        Analysis results dictionary
    """
    if not items:
        logging.warning(f"No items found in {collection_name}")
        return {
            'collection_path': collection_name,
            'collection_key': collection_key,
            'total_items': 0,
            'analyzed_items': 0,
            'successful_analyses': 0,
            'failed_analyses': 0,
            'skipped_analyses': 0,
            'skipped_no_fulltext': [],
            'skipped_already_analyzed': [],
            'failed_items': [],
            'results': []
        }
    
    logging.info(f"Found {len(items)} items to analyze in {collection_name}")
    
    # Analyze each item
    results = []
    successful_analyses = 0
    failed_analyses = 0
    skipped_analyses = 0
    skipped_no_fulltext = []
    skipped_already_analyzed = []
    failed_items = []
    
    for i, item in enumerate(items, 1):
        item_id = item.get('key')
        title = item.get('data', {}).get('title', 'Unknown Title')
        
        logging.info(f"Processing item {i}/{len(items)}: {title}")
        
        try:
            # Use the existing analyze_item function
            result = analyze_item(zot, item_id, config, skip_analyzed, task_name)
            results.append(result)
            
            if result.get('skipped', False):
                skipped_analyses += 1
                skip_reason = result.get('skip_reason', '')
                if 'No fulltext available' in skip_reason:
                    skipped_no_fulltext.append(title)
                elif 'Already analyzed' in skip_reason:
                    skipped_already_analyzed.append(title)
                logging.info(f"Skipped item {i}/{len(items)}: {title} ({skip_reason})")
            else:
                successful_analyses += 1
                logging.info(f"Successfully analyzed item {i}/{len(items)}: {title}")
            
        except Exception as e:
            logging.error(f"Failed to analyze item {i}/{len(items)} ({title}): {e}")
            failed_analyses += 1
            failed_items.append(f"({item_id}) {title}: {str(e)}")
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
    
    result_dict = {
        'collection_path': collection_name,
        'collection_key': collection_key,
        'total_items': len(items),
        'analyzed_items': len(results),
        'successful_analyses': successful_analyses,
        'failed_analyses': failed_analyses,
        'skipped_analyses': skipped_analyses,
        'skipped_no_fulltext': skipped_no_fulltext,
        'skipped_already_analyzed': skipped_already_analyzed,
        'failed_items': failed_items,
        'results': results
    }
    
    logging.info(f"{collection_name} analysis completed: {successful_analyses}/{len(items)} items successfully analyzed, {skipped_analyses} skipped")
    
    return result_dict


def analyze_collection(zot, collection_path: str, config: Dict[str, Any], skip_analyzed: bool = False, task_name: str = 'llm_summary') -> Dict[str, Any]:
    """
    Analyze all items in a Zotero collection and its subcollections using LLM.
    
    Args:
        zot: Zotero client instance
        collection_path: Slash-separated path to the collection (e.g., 'a/b/c')
        config: Configuration dictionary
        skip_analyzed: If True, skip items that already have task-specific tags
        task_name: Name of the task to perform
        
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
        
        # Reuse the shared analysis logic
        return _analyze_items_list(zot, items, config, skip_analyzed, task_name, collection_path, collection_key)
        
    except Exception as e:
        logging.error(f"Failed to analyze collection at path '{collection_path}': {e}")
        raise


def analyze_unfiled_items(zot, config: Dict[str, Any], skip_analyzed: bool = False, task_name: str = 'llm_summary') -> Dict[str, Any]:
    """
    Analyze all unfiled items (items not in any collection) using LLM.
    
    Args:
        zot: Zotero client instance
        config: Configuration dictionary
        skip_analyzed: If True, skip items that already have task-specific tags
        task_name: Name of the task to perform
        
    Returns:
        Analysis results dictionary
    """
    try:
        # Get all unfiled items
        unfiled_items = main.get_unfiled_items(zot)
        
        if not unfiled_items:
            logging.warning("No unfiled items found")
            return {
                'collection_path': 'Unfiled Items',
                'collection_key': None,
                'total_items': 0,
                'analyzed_items': 0,
                'successful_analyses': 0,
                'failed_analyses': 0,
                'skipped_analyses': 0,
                'skipped_no_fulltext': [],
                'skipped_already_analyzed': [],
                'failed_items': [],
                'results': []
            }
        
        logging.info(f"Found {len(unfiled_items)} unfiled items to analyze")
        
        # Reuse the existing collection analysis logic with unfiled items
        return _analyze_items_list(zot, unfiled_items, config, skip_analyzed, task_name, 'Unfiled Items')
        
    except Exception as e:
        logging.error(f"Failed to analyze unfiled items: {e}")
        raise


def manage_missing_pdf_flags(zot, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Database-level task to manage missing_pdf flags on all items.
    
    Args:
        zot: Zotero client instance
        config: Configuration dictionary
        
    Returns:
        Results dictionary with statistics and processed items
    """
    try:
        logging.info("Starting missing_pdf flag management for entire library")
        
        # Get all items and collections in bulk (efficient)
        logging.info("Fetching all items and collections...")
        all_items = zot.everything(zot.items())
        all_collections = zot.everything(zot.collections())
        
        # Create lookup dictionaries for efficiency
        collections_by_key = {col['key']: col for col in all_collections}
        
        # Separate parent items and attachments
        parent_items = [item for item in all_items if not item['data'].get('parentItem')]
        attachments = [item for item in all_items if item['data'].get('itemType') == 'attachment']
        
        logging.info(f"Found {len(parent_items)} parent items and {len(attachments)} attachments")
        
        # Build PDF availability lookup (no individual API calls!)
        items_with_pdfs = set()
        for attachment in attachments:
            if (attachment['data'].get('contentType') == 'application/pdf' and 
                attachment['data'].get('parentItem')):
                items_with_pdfs.add(attachment['data']['parentItem'])
        
        logging.info(f"Found {len(items_with_pdfs)} items with PDF attachments")
        
        # Process parent items efficiently
        flags_added = []
        flags_removed = []
        errors = []
        items_missing_pdfs = []
        
        for i, item in enumerate(parent_items, 1):
            item_id = item.get('key')
            title = item.get('data', {}).get('title', 'Unknown Title')
            
            if i % 100 == 0:  # Progress logging every 100 items
                logging.info(f"Processed {i}/{len(parent_items)} items...")
            
            try:
                # Check PDF availability from our lookup (no API call!)
                has_pdf = item_id in items_with_pdfs
                
                # Get current tags
                current_tags = item.get('data', {}).get('tags', [])
                current_tag_names = [tag.get('tag', '').lower() for tag in current_tags]
                has_missing_pdf_tag = 'missing_pdf' in current_tag_names
                
                # Get item collections from the collections we already fetched
                collection_keys = item.get('data', {}).get('collections', [])
                collection_names = []
                for collection_key in collection_keys:
                    if collection_key in collections_by_key:
                        # Build full path for nested collections
                        path_parts = []
                        current_collection = collections_by_key[collection_key]
                        
                        # Walk up the hierarchy
                        while current_collection:
                            path_parts.insert(0, current_collection['data'].get('name', 'Unknown'))
                            parent_key = current_collection['data'].get('parentCollection')
                            current_collection = collections_by_key.get(parent_key) if parent_key else None
                        
                        collection_names.append('/'.join(path_parts))
                
                collection_display = ', '.join(collection_names) if collection_names else 'Unfiled'
                
                if not has_pdf:
                    # Item missing PDF
                    items_missing_pdfs.append({
                        'title': title,
                        'item_id': item_id,
                        'collections': collection_display
                    })
                    
                    # Add missing_pdf tag if not present
                    if not has_missing_pdf_tag:
                        success = main.add_tag_to_item(zot, item_id, 'missing_pdf')
                        if success:
                            flags_added.append({
                                'title': title,
                                'item_id': item_id,
                                'collections': collection_display
                            })
                            logging.info(f"Added missing_pdf flag to: {title}")
                        else:
                            logging.warning(f"Failed to add missing_pdf flag to: {title}")
                else:
                    # Item has PDF - remove flag if present
                    if has_missing_pdf_tag:
                        success = main.remove_tag_from_item(zot, item_id, 'missing_pdf')
                        if success:
                            flags_removed.append({
                                'title': title,
                                'item_id': item_id,
                                'collections': collection_display
                            })
                            logging.info(f"Removed missing_pdf flag from: {title}")
                        else:
                            logging.warning(f"Failed to remove missing_pdf flag from: {title}")
                
            except Exception as e:
                error_msg = f"({item_id}) {title}: {str(e)}"
                errors.append(error_msg)
                logging.error(f"Error processing item {title}: {e}")
        
        # Compile results
        result = {
            'total_items': len(parent_items),
            'items_with_pdfs': len(items_with_pdfs),
            'items_without_pdfs': len(items_missing_pdfs),
            'flags_added': len(flags_added),
            'flags_removed': len(flags_removed),
            'errors': len(errors),
            'items_missing_pdf': items_missing_pdfs,
            'flags_added_details': flags_added,
            'flags_removed_details': flags_removed,
            'error_details': errors
        }
        
        logging.info(f"Missing PDF flag management completed: {len(parent_items)} items processed, "
                    f"{len(flags_added)} flags added, {len(flags_removed)} flags removed, "
                    f"{len(errors)} errors")
        
        return result
        
    except Exception as e:
        logging.error(f"Failed to manage missing_pdf flags: {e}")
        raise


def analyze_multiple_collections(zot, collection_paths: List[str], config: Dict[str, Any], skip_analyzed: bool = False, task_name: str = 'llm_summary') -> List[Dict[str, Any]]:
    """
    Analyze multiple Zotero collections using LLM.
    
    Args:
        zot: Zotero client instance
        collection_paths: List of slash-separated paths to collections (e.g., ['a/b', 'c/d'])
        config: Configuration dictionary
        skip_analyzed: If True, skip items that already have task-specific tags
        task_name: Name of the task to perform
        
    Returns:
        List of analysis results dictionaries (one per collection)
    """
    results = []
    
    for i, collection_path in enumerate(collection_paths, 1):
        logging.info(f"Processing collection {i}/{len(collection_paths)}: {collection_path}")
        
        try:
            # Analyze this collection
            result = analyze_collection(zot, collection_path, config, skip_analyzed, task_name)
            results.append(result)
            
            logging.info(f"Completed collection {i}/{len(collection_paths)}: {collection_path} "
                        f"({result['successful_analyses']}/{result['total_items']} items processed)")
            
        except Exception as e:
            logging.error(f"Failed to analyze collection {i}/{len(collection_paths)} ({collection_path}): {e}")
            # Add a failed result to maintain structure
            results.append({
                'collection_path': collection_path,
                'collection_key': None,
                'total_items': 0,
                'analyzed_items': 0,
                'successful_analyses': 0,
                'failed_analyses': 0,
                'skipped_analyses': 0,
                'skipped_no_fulltext': [],
                'skipped_already_analyzed': [],
                'failed_items': [f"Collection processing failed: {str(e)}"],
                'results': [],
                'error': str(e)
            })
    
    total_collections = len(collection_paths)
    successful_collections = len([r for r in results if not r.get('error')])
    
    logging.info(f"Multiple collections analysis completed: {successful_collections}/{total_collections} collections processed successfully")
    
    return results


