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


def summary_qa_collection(zot, collection_path: str, question: str, config: Dict[str, Any], include_references: bool = True) -> Dict[str, Any]:
    """
    Answer questions using LLM summaries and optionally key references from all items in a collection.
    
    Args:
        zot: Zotero client instance
        collection_path: Slash-separated path to the collection (e.g., 'a/b/c')
        question: User question to answer
        config: Configuration dictionary
        include_references: If True, include Key References notes with summaries
        
    Returns:
        Results dictionary with answer and metadata
    """
    try:
        # Find the collection by path
        collection_key = main.find_collection_by_path(zot, collection_path)
        if not collection_key:
            raise ValueError(f"Collection not found at path: {collection_path}")
        
        # Get all items from the collection and its subcollections
        items = main.get_collection_items(zot, collection_key, recursive=True)
        
        if not items:
            logging.warning(f"No items found in collection {collection_path}")
            return {
                'collection_path': collection_path,
                'collection_key': collection_key,
                'question': question,
                'answer': "No items found in the specified collection.",
                'total_items': 0,
                'items_with_summaries': 0,
                'items_with_references': 0,
                'items_processed': [],
                'items_skipped': []
            }
        
        logging.info(f"Found {len(items)} items in collection {collection_path}")
        
        # Collect summaries and references from items
        summaries_data = []
        items_processed = []
        items_skipped = []
        
        for item in items:
            item_id = item.get('key')
            title = item.get('data', {}).get('title', 'Unknown Title')
            authors = item.get('data', {}).get('creators', [])
            author_names = [f"{c.get('firstName', '')} {c.get('lastName', '')}" for c in authors]
            
            # Check if item has LLM summary tag
            tags = item.get('data', {}).get('tags', [])
            tag_names = [tag.get('tag', '').lower() for tag in tags]
            has_summary = 'llm_summary' in tag_names
            has_references = 'key_references' in tag_names
            
            if not has_summary:
                logging.info(f"Skipping item without LLM summary: {title}")
                items_skipped.append({
                    'title': title,
                    'item_id': item_id,
                    'reason': 'No LLM summary available'
                })
                continue
            
            # Get LLM Summary note
            summary_content = _get_note_content(zot, item_id, "LLM Summary")
            if not summary_content:
                logging.warning(f"LLM Summary tag found but no note content for: {title}")
                items_skipped.append({
                    'title': title,
                    'item_id': item_id,
                    'reason': 'LLM summary tag present but no note content found'
                })
                continue
            
            # Optionally get Key References note
            references_content = ""
            if include_references and has_references:
                references_content = _get_note_content(zot, item_id, "Key References")
                if not references_content:
                    logging.info(f"Key References tag found but no note content for: {title}")
            
            # Add to summaries data
            paper_data = {
                'title': title,
                'authors': ', '.join(author_names) if author_names else 'Unknown Authors',
                'item_id': item_id,
                'summary': summary_content,
                'references': references_content if include_references else ""
            }
            summaries_data.append(paper_data)
            items_processed.append({
                'title': title,
                'item_id': item_id,
                'has_references': bool(references_content)
            })
            
            logging.info(f"Collected data for: {title}")
        
        if not summaries_data:
            return {
                'collection_path': collection_path,
                'collection_key': collection_key,
                'question': question,
                'answer': "No items with LLM summaries found in the collection. Please run 'llm_summary' task first.",
                'total_items': len(items),
                'items_with_summaries': 0,
                'items_with_references': 0,
                'items_processed': items_processed,
                'items_skipped': items_skipped
            }
        
        logging.info(f"Collected summaries from {len(summaries_data)} items, answering question...")
        
        # Generate the comprehensive prompt with all summaries
        papers_text = _format_papers_for_qa(summaries_data, include_references)
        qa_response = _answer_question_with_summaries(question, papers_text, config)
        
        # Extract title and answer from response
        qa_title = qa_response["title"]
        qa_answer = qa_response["answer"]
        
        # Create QA note using the simple, proven approach
        model_name = config.get('llm', {}).get('model', 'Unknown Model')
        note_created, note_result = create_qa_note_simple(
            zot, collection_path, question, qa_title, qa_answer, model_name, summaries_data
        )
        
        result = {
            'collection_path': collection_path,
            'collection_key': collection_key,
            'question': question,
            'answer': qa_answer,
            'qa_title': qa_title,
            'note_created': note_created,
            'note_key': note_result if note_created else None,
            'note_error': note_result if not note_created else None,
            'total_items': len(items),
            'items_with_summaries': len(summaries_data),
            'items_with_references': len([p for p in summaries_data if p['references']]),
            'items_processed': items_processed,
            'items_skipped': items_skipped
        }
        
        logging.info(f"Summary Q&A completed for collection {collection_path}: {len(summaries_data)} summaries processed")
        return result
        
    except Exception as e:
        logging.error(f"Failed to perform summary Q&A for collection '{collection_path}': {e}")
        raise


def _get_note_content(zot, item_id: str, note_title: str) -> str:
    """
    Get the content of a specific note by title for an item.
    
    Args:
        zot: Zotero client instance
        item_id: Zotero item ID
        note_title: Title of the note to find (e.g., "LLM Summary", "Key References")
        
    Returns:
        Note content as string, or empty string if not found
    """
    try:
        # Get all children of this item
        children = zot.children(item_id)
        
        # Find notes that match the title
        for child in children:
            if child.get('data', {}).get('itemType') == 'note':
                note_content = child.get('data', {}).get('note', '')
                # Check if this note has the right title (look for the title in HTML)
                if f"<h2>{note_title}</h2>" in note_content:
                    # Extract the content after the title and model info
                    # Remove HTML tags and clean up
                    import re
                    # Remove HTML tags
                    clean_content = re.sub(r'<[^>]+>', '', note_content)
                    # Remove the title and model lines
                    lines = clean_content.split('\n')
                    content_lines = []
                    skip_next = False
                    for line in lines:
                        line = line.strip()
                        if line.startswith(note_title) or line.startswith('Model:'):
                            skip_next = True
                            continue
                        if skip_next and not line:
                            skip_next = False
                            continue
                        if not skip_next and line:
                            content_lines.append(line)
                        skip_next = False
                    
                    return '\n'.join(content_lines).strip()
        
        return ""
        
    except Exception as e:
        logging.warning(f"Failed to get note content for item {item_id}: {e}")
        return ""


def _format_papers_for_qa(papers_data: List[Dict[str, Any]], include_references: bool) -> str:
    """
    Format papers data for the Q&A prompt.
    
    Args:
        papers_data: List of paper dictionaries with title, authors, summary, references
        include_references: Whether to include references in the output
        
    Returns:
        Formatted string with all papers
    """
    formatted_papers = []
    
    for i, paper in enumerate(papers_data, 1):
        paper_text = f"""
Paper {i}: {paper['title']}
Authors: {paper['authors']}

LLM Summary:
{paper['summary']}"""
        
        if include_references and paper['references']:
            paper_text += f"""

Key References:
{paper['references']}"""
        
        formatted_papers.append(paper_text)
    
    return "\n\n" + "="*80 + "\n\n".join(formatted_papers)


def _answer_question_with_summaries(question: str, papers_text: str, config: Dict[str, Any]) -> str:
    """
    Use LLM to answer a question based on the provided paper summaries.
    
    Args:
        question: User's question
        papers_text: Formatted text with all paper summaries
        config: Configuration dictionary
        
    Returns:
        LLM answer to the question
    """
    # Load prompts configuration
    prompts_file = config.get('prompts_file', 'prompts.yaml')
    prompts_config = main.load_prompts(prompts_file)
    
    # Get summary_qa prompt
    task_prompt = prompts_config.get('tasks', {}).get('summary_qa', {}).get('prompt', '')
    if not task_prompt:
        raise ValueError("No prompt found for 'summary_qa' in the prompts configuration. Please check your prompts.yaml file.")
    
    # Prepare the full prompt
    content_prompt = f"""
{task_prompt}

User Question: {question}

Research Papers from Collection:
{papers_text}

Please answer the user's question based on the provided summaries and references."""
    
    # Check if the prompt exceeds the maximum length (if configured)
    config_section = config.get('tasks', {}).get('summary_qa', {})
    max_prompt_chars = config_section.get('max_prompt_chars')
    
    if max_prompt_chars is not None:
        if len(content_prompt) > max_prompt_chars:
            raise ValueError(
                f"Prompt too large ({len(content_prompt):,} characters). "
                f"Maximum allowed: {max_prompt_chars:,} characters. "
                f"Either increase max_prompt_chars in config or process fewer papers."
            )
    
    # Create a copy of config with enhanced timeout for summary_qa
    qa_config = config.copy()
    llm_config = qa_config.get('llm', {}).copy()
    
    # Set a longer timeout for summary_qa if not already configured
    if 'timeout' not in llm_config:
        # Use longer timeouts for complex Q&A tasks
        current_timeout = llm_config.get('timeout', 60)
        enhanced_timeout = max(current_timeout * 3, 180)  # At least 3 minutes
        llm_config['timeout'] = enhanced_timeout
        logging.info(f"Using enhanced timeout of {enhanced_timeout}s for summary_qa task")
    
    qa_config['llm'] = llm_config
    
    response = llm.call_llm(content_prompt, qa_config)
    
    # Parse the response to extract title and answer
    title, answer = _parse_qa_response(response)
    
    return {"title": title, "answer": answer, "full_response": response}


def _parse_qa_response(response: str) -> tuple[str, str]:
    """
    Parse the LLM response to extract title and answer.
    
    Args:
        response: Full LLM response containing TITLE: and ANSWER: sections
        
    Returns:
        Tuple of (title, answer)
    """
    try:
        lines = response.strip().split('\n')
        title = "QA Response"  # Default title
        answer = response  # Default to full response
        
        title_found = False
        answer_lines = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('TITLE:'):
                title = line.replace('TITLE:', '').strip()
                title_found = True
            elif line.startswith('ANSWER:'):
                # Start collecting answer lines
                continue
            elif title_found:
                # Collect all lines after ANSWER: as the answer
                answer_lines.append(line)
        
        if answer_lines:
            answer = '\n'.join(answer_lines).strip()
        
        # Clean up title - remove any unwanted characters and limit length
        title = title.replace('"', '').replace("'", "").strip()
        if len(title) > 50:
            title = title[:47] + "..."
        
        return title, answer
        
    except Exception as e:
        logging.warning(f"Failed to parse QA response format: {e}")
        # Fallback to using response as answer and default title
        return "QA Response", response


def get_all_collection_paths(zot) -> List[str]:
    """
    Get all collection paths in hierarchical format, reusing existing logic.
    
    Args:
        zot: Zotero client instance
        
    Returns:
        List of collection paths (e.g., ['Research/AI', 'Papers/NLP', 'Books'])
    """
    try:
        # Get all collections using existing function
        all_collections = main.get_collections(zot)
        
        # Build paths using the same logic as get_item_collections
        collections_by_key = {col['key']: col for col in all_collections}
        collection_paths = []
        
        for collection in all_collections:
            # Build full path using existing logic pattern
            path_parts = []
            current_collection = collection
            
            while current_collection:
                path_parts.insert(0, current_collection['data'].get('name', 'Unknown'))
                parent_key = current_collection['data'].get('parentCollection')
                current_collection = collections_by_key.get(parent_key) if parent_key else None
            
            collection_paths.append('/'.join(path_parts))
        
        # Filter out the #LLM QA collection and all its subcollections to avoid processing Q&A notes
        collection_paths = [path for path in collection_paths if not path.startswith("#LLM QA")]
        
        # Sort for consistent ordering
        collection_paths.sort()
        
        logging.info(f"Found {len(collection_paths)} collections (excluding #LLM QA and subcollections)")
        return collection_paths
        
    except Exception as e:
        logging.error(f"Failed to get all collection paths: {e}")
        return []


def find_or_create_collection(zot, collection_path: str) -> tuple[bool, str]:
    """
    Generic function to find or create a collection by path.
    Supports both simple names ("MyCollection") and paths ("#LLM QA/Complex Networks").
    
    Args:
        zot: Zotero client instance
        collection_path: Name or path of the collection to find or create
        
    Returns:
        Tuple of (success, collection_key or error_message)
    """
    try:
        # Split path into parts
        path_parts = [part.strip() for part in collection_path.strip('/').split('/') if part.strip()]
        if not path_parts:
            return False, "Empty collection path provided"
        
        # Get all collections
        all_collections = zot.everything(zot.collections())
        collections_by_key = {col['key']: col for col in all_collections}
        
        # Start with top-level collections
        current_collections = [col for col in all_collections if not col['data'].get('parentCollection')]
        parent_key = None
        
        # Navigate/create through the path
        for i, part in enumerate(path_parts):
            # Look for existing collection at current level
            found_collection = None
            for col in current_collections:
                if col['data'].get('name') == part:
                    found_collection = col
                    break
            
            if found_collection:
                # Collection exists, use it
                collection_key = found_collection['key']
                logging.info(f"Found existing collection '{part}' with key: {collection_key}")
                
                if i == len(path_parts) - 1:
                    # This is the final collection we want
                    return True, collection_key
                
                # Move to subcollections for next iteration
                parent_key = collection_key
                current_collections = [
                    col for col in all_collections 
                    if col['data'].get('parentCollection') == parent_key
                ]
            else:
                # Collection doesn't exist, create it
                logging.info(f"Creating new collection '{part}'" + 
                           (f" under parent {parent_key}" if parent_key else " at top level"))
                
                collection_data = {"name": part}
                if parent_key:
                    collection_data["parentCollection"] = parent_key
                
                result = zot.create_collections([collection_data])
                logging.debug(f"Collection creation result: {result}")
                
                if result and "success" in result and result["success"]:
                    collection_key = next(iter(result["success"].keys()))
                    logging.info(f"Created collection '{part}' with key: {collection_key}")
                elif result and "successful" in result and result["successful"]:
                    collection_key = next(iter(result["successful"].keys()))
                    logging.info(f"Created collection '{part}' with key: {collection_key}")
                else:
                    error_msg = f"Failed to create collection '{part}': {result}"
                    logging.error(error_msg)
                    return False, error_msg
                
                if i == len(path_parts) - 1:
                    # This is the final collection we want
                    return True, collection_key
                
                # Set up for next iteration
                parent_key = collection_key
                current_collections = []  # No subcollections exist yet for newly created collection
        
        return False, "Unexpected end of path processing"
            
    except Exception as e:
        error_msg = f"Error finding/creating collection '{collection_path}': {e}"
        logging.error(error_msg)
        return False, error_msg


def create_qa_note_simple(zot, source_collection_path: str, question: str, title: str, answer: str, model_name: str, papers_data: List[Dict[str, Any]]) -> tuple[bool, str]:
    """
    Create a QA note. SIMPLE VERSION.
    """
    try:
        # Extract top-level collection name from source path
        path_parts = [part.strip() for part in source_collection_path.strip('/').split('/') if part.strip()]
        if not path_parts:
            return False, "Invalid source collection path: empty or invalid"
        
        top_level_collection = path_parts[0]
        target_collection_path = f"#LLM QA/{top_level_collection}"
        
        # Find or create the target collection (will create both #LLM QA and subcollection as needed)
        collection_success, target_collection_key = find_or_create_collection(zot, target_collection_path)
        if not collection_success:
            return False, f"Failed to create collection: {target_collection_key}"
        
        # Generate papers list
        papers_list = "\n".join([
            f"{i}. {paper['title']} ({paper['authors']})"
            for i, paper in enumerate(papers_data, 1)
        ])
        
        # Create the note content
        unique_title = f"{source_collection_path}: {title}"
        content = f"""<h2>{unique_title}</h2>
<p><strong>Model:</strong> {model_name}</p>
<p><strong>Source Collection:</strong> {source_collection_path}</p>
<p><strong>Question:</strong> {question}</p>
<p><strong>Answer:</strong></p>
<pre>{answer}</pre>

<p><strong>Papers Analyzed ({len(papers_data)} total):</strong></p>
<pre>{papers_list}</pre>"""
        
        # Create note directly with Zotero API
        note_data = {
            "itemType": "note",
            "note": content,
            "tags": [{"tag": "llm_qa"}],
            "collections": [target_collection_key]
        }
        
        result = zot.create_items([note_data])
        
        if result and "success" in result and result["success"]:
            note_key = next(iter(result["success"].keys()))
            logging.info(f"Created QA note '{unique_title}' (key: {note_key})")
            return True, note_key
        else:
            logging.error(f"Note creation failed: {result}")
            return False, f"API returned: {result}"
            
    except Exception as e:
        logging.error(f"Error creating QA note: {e}")
        return False, str(e)


