#!/usr/bin/env python3
"""
Zotero LLM Assistant CLI Entry Point

This script serves as the main entry point for the Zotero LLM organization tool.
It handles command-line arguments and coordinates between the main module and tasks.
"""

import argparse
import sys
import logging
from zotero_llm import main, tasks


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Zotero LLM Assistant - Analyze and organize your research library"
    )
    
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    
    parser.add_argument(
        'task',
        choices=['llm_summary', 'key_references', 'missing_pdf', 'summary_qa'],
        help='Task to perform'
    )
    
    parser.add_argument(
        'object_type',
        nargs='?',
        choices=['item', 'collection'],
        help='Type of object to process (required for item/collection tasks)'
    )
    
    parser.add_argument(
        '--item-id',
        help='Zotero item ID to analyze'
    )
    
    parser.add_argument(
        '--collection-path',
        nargs='+',
        help='Hierarchical path(s) to Zotero collection(s) (e.g., "folder/subfolder" or multiple: "collection1" "collection2")'
    )
    
    parser.add_argument(
        '--unfiled',
        action='store_true',
        help='Process unfiled items (items not assigned to any collection)'
    )
    
    parser.add_argument(
        '--all-collections',
        action='store_true',
        help='Process all collections in the library (collection-level tasks only)'
    )
    
    parser.add_argument(
        '--query',
        help='Search query to find items'
    )
    
    parser.add_argument(
        '--question',
        help='Question to ask when using summary_qa task'
    )
    
    parser.add_argument(
        '--references',
        action='store_true',
        default=True,
        help='Include Key References with summaries in summary_qa (default: True)'
    )
    
    parser.add_argument(
        '--no-references',
        dest='references',
        action='store_false',
        help='Do not include Key References with summaries in summary_qa'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )
    
    parser.add_argument(
        '--skip-analyzed',
        action='store_true',
        default=True,
        help='Skip items that already have the llm_summary tag (default: True)'
    )
    
    parser.add_argument(
        '--no-skip-analyzed',
        dest='skip_analyzed',
        action='store_false',
        help='Process all items, even those already analyzed'
    )
    
    return parser.parse_args()


def main_cli():
    """Main CLI entry point."""
    args = parse_arguments()
    
    # Setup logging
    log_level = 'DEBUG' if args.verbose else args.log_level
    main.setup_logging(log_level)
    
    try:
        # Load configuration
        config = main.load_config(args.config)
        
        # Get Zotero client
        zot = main.get_zotero_client(config)
        
        # Check if task requires an object type
        if args.task in ['llm_summary', 'key_references']:
            if not args.object_type:
                print(f"Error: object type (item or collection) required for {args.task} task")
                sys.exit(1)
        elif args.task == 'summary_qa':
            # summary_qa only works on collections
            if not args.object_type or args.object_type != 'collection':
                print(f"Error: summary_qa task only works on collections")
                sys.exit(1)
            if not args.question:
                print(f"Error: --question required for summary_qa task")
                sys.exit(1)
        
        # Execute task based on arguments
        if args.object_type == 'item':
            if not args.item_id and not args.query:
                print(f"Error: --item-id or --query required for item {args.task} task")
                sys.exit(1)
            
            # If query provided, search for items first
            if args.query:
                items = main.search_items(zot, args.query, limit=1)
                if not items:
                    print(f"No items found for query: '{args.query}'")
                    sys.exit(1)
                item_id = items[0]['key']
                print(f"Found item: {items[0]['data'].get('title', 'Unknown')}")
            else:
                item_id = args.item_id
            
            # Process the item with the specified task
            result = tasks.analyze_item(zot, item_id, config, args.skip_analyzed, args.task)
            
            # Print result for individual item
            if result.get('skipped', False):
                print(f"Item skipped: {result.get('skip_reason', 'Already processed')}")
            else:
                print(f"{args.task} completed for item: {result['title']}")
            
        elif args.object_type == 'collection':
            if args.all_collections:
                # Get all collection paths
                all_collection_paths = tasks.get_all_collection_paths(zot)
                if not all_collection_paths:
                    print(f"No collections found in library")
                    sys.exit(1)
                
                if args.task == 'summary_qa':
                    # For summary_qa, process each collection individually
                    total_successful_qa = 0
                    total_failed_qa = 0
                    qa_results = []
                    
                    for i, collection_path in enumerate(all_collection_paths, 1):
                        print(f"\nProcessing collection {i}/{len(all_collection_paths)}: {collection_path}")
                        try:
                            result = tasks.summary_qa_collection(zot, collection_path, args.question, config, args.references)
                            qa_results.append(result)
                            
                            if result.get('note_created'):
                                total_successful_qa += 1
                                print(f"✅ Created QA note: {result.get('qa_title', 'Unknown')}")
                            else:
                                total_failed_qa += 1
                                print(f"❌ Failed: {result.get('note_error', 'Unknown error')}")
                                
                        except Exception as e:
                            total_failed_qa += 1
                            print(f"❌ Failed to process collection {collection_path}: {e}")
                    
                    # Print overall summary for summary_qa
                    print(f"\nSummary Q&A Results for All Collections:")
                    print(f"  Total Collections: {len(all_collection_paths)}")
                    print(f"  Successful Q&A Notes: {total_successful_qa}")
                    print(f"  Failed: {total_failed_qa}")
                    print(f"  Question: {args.question}")
                    
                    sys.exit(0)  # Exit early since we handled summary_qa specially
                
                # Process all collections using existing multi-collection logic
                all_results = tasks.analyze_multiple_collections(zot, all_collection_paths, config, args.skip_analyzed, args.task)
                
                # Print overall summary (reusing existing code)
                total_items = sum(result['total_items'] for result in all_results)
                total_successful = sum(result['successful_analyses'] for result in all_results)
                total_failed = sum(result['failed_analyses'] for result in all_results)
                total_skipped = sum(result['skipped_analyses'] for result in all_results)
                
                print(f"\nAll Collections {args.task} Summary:")
                print(f"  Collections Processed: {len(all_collection_paths)}")
                print(f"  Total Items: {total_items}")
                print(f"  Successfully Processed: {total_successful}")
                print(f"  Failed: {total_failed}")
                print(f"  Skipped Items: {total_skipped}")
                
                # Print per-collection breakdown
                print(f"\nPer-Collection Breakdown:")
                for result in all_results:
                    print(f"  {result['collection_path']}: {result['successful_analyses']}/{result['total_items']} processed")
                
                # Aggregate skip/fail information
                all_skipped_no_fulltext = []
                all_failed_items = []
                
                for result in all_results:
                    if result.get('skipped_no_fulltext'):
                        all_skipped_no_fulltext.extend(result['skipped_no_fulltext'])
                    if result.get('failed_items'):
                        all_failed_items.extend(result['failed_items'])
                
                # Print detailed skip/fail information
                if all_skipped_no_fulltext:
                    print(f"\nItems skipped (no fulltext):")
                    for title in all_skipped_no_fulltext:
                        print(f"  - {title}")
                        
                if all_failed_items:
                    print(f"\nItems that failed:")
                    for item_error in all_failed_items:
                        print(f"  - {item_error}")
            elif args.unfiled:
                # Process unfiled items
                result = tasks.analyze_unfiled_items(zot, config, args.skip_analyzed, args.task)
                
                # Print summary
                print(f"\nUnfiled Items {args.task} Summary:")
                print(f"  Total Items: {result['total_items']}")
                print(f"  Successfully Processed: {result['successful_analyses']}")
                print(f"  Failed: {result['failed_analyses']}")
                print(f"  Skipped Items: {result['skipped_analyses']}")
                
                # Print detailed skip/fail information
                if result.get('skipped_no_fulltext'):
                    print(f"\nItems skipped (no fulltext):")
                    for title in result['skipped_no_fulltext']:
                        print(f"  - {title}")
                        
                if result.get('failed_items'):
                    print(f"\nItems that failed:")
                    for item_error in result['failed_items']:
                        print(f"  - {item_error}")
                        
            elif args.collection_path:
                if args.task == 'summary_qa':
                    # Handle summary_qa task separately since it has different signature
                    if len(args.collection_path) > 1:
                        print(f"Error: summary_qa task can only process one collection at a time")
                        sys.exit(1)
                    
                    collection_path = args.collection_path[0]
                    result = tasks.summary_qa_collection(zot, collection_path, args.question, config, args.references)
                    
                    # Print summary_qa results
                    print(f"\nSummary Q&A Results for Collection: {result['collection_path']}")
                    print(f"  Question: {result['question']}")
                    print(f"  Total Items: {result['total_items']}")
                    print(f"  Items with Summaries: {result['items_with_summaries']}")
                    print(f"  Items with References: {result['items_with_references']}")
                    
                    # Print note creation status
                    if result.get('note_created'):
                        print(f"\n✅ QA Note Created:")
                        print(f"  Title: {result.get('qa_title', 'QA Response')}")
                        print(f"  Note Key: {result.get('note_key')}")
                        print(f"  Location: '#LLM QA' collection")
                        print(f"  Source: Collection '{result['collection_path']}'")
                        print(f"  Tag: llm_qa")
                    else:
                        print(f"\n❌ Failed to create QA note:")
                        print(f"  Error: {result.get('note_error', 'Unknown error')}")
                        print(f"\nAnswer preview (first 500 chars):")
                        answer_preview = result.get('answer', '')[:500]
                        if len(result.get('answer', '')) > 500:
                            answer_preview += "..."
                        print(f"{answer_preview}")
                    
                    # Print items processed/skipped if any
                    if result.get('items_skipped'):
                        print(f"\nItems skipped:")
                        for item in result['items_skipped']:
                            print(f"  - {item['title']} ({item['reason']})")
                else:
                    # Process multiple collections with the specified task
                    all_results = tasks.analyze_multiple_collections(zot, args.collection_path, config, args.skip_analyzed, args.task)
                    
                    # Print overall summary
                    total_items = sum(result['total_items'] for result in all_results)
                    total_successful = sum(result['successful_analyses'] for result in all_results)
                    total_failed = sum(result['failed_analyses'] for result in all_results)
                    total_skipped = sum(result['skipped_analyses'] for result in all_results)
                    
                    print(f"\nMultiple Collections {args.task} Summary:")
                    print(f"  Collections Processed: {len(args.collection_path)}")
                    print(f"  Total Items: {total_items}")
                    print(f"  Successfully Processed: {total_successful}")
                    print(f"  Failed: {total_failed}")
                    print(f"  Skipped Items: {total_skipped}")
                    
                    # Print per-collection breakdown
                    print(f"\nPer-Collection Breakdown:")
                    for result in all_results:
                        print(f"  {result['collection_path']}: {result['successful_analyses']}/{result['total_items']} processed")
                    
                    # Aggregate skip/fail information
                    all_skipped_no_fulltext = []
                    all_failed_items = []
                    
                    for result in all_results:
                        if result.get('skipped_no_fulltext'):
                            all_skipped_no_fulltext.extend(result['skipped_no_fulltext'])
                        if result.get('failed_items'):
                            all_failed_items.extend(result['failed_items'])
                    
                    # Print detailed skip/fail information
                    if all_skipped_no_fulltext:
                        print(f"\nItems skipped (no fulltext):")
                        for title in all_skipped_no_fulltext:
                            print(f"  - {title}")
                            
                    if all_failed_items:
                        print(f"\nItems that failed:")
                        for item_error in all_failed_items:
                            print(f"  - {item_error}")
            else:
                print(f"Error: --collection-path, --unfiled, or --all-collections required for collection {args.task} task")
                sys.exit(1)
                
        elif args.object_type:
            print(f"Unknown object type: {args.object_type}")
            sys.exit(1)
        elif args.task == 'missing_pdf':
            # Handle missing_pdf database-level task
            result = tasks.manage_missing_pdf_flags(zot, config)
            
            # Print summary
            print(f"\nMissing PDF Management Summary:")
            print(f"  Total Items Processed: {result['total_items']}")
            print(f"  Items with PDFs: {result['items_with_pdfs']}")
            print(f"  Items without PDFs: {result['items_without_pdfs']}")
            print(f"  Flags Added: {result['flags_added']}")
            print(f"  Flags Removed: {result['flags_removed']}")
            print(f"  Errors: {result['errors']}")
            
            # Print items missing PDFs
            if result['items_missing_pdf']:
                print(f"\nItems Missing PDFs:")
                for item in result['items_missing_pdf']:
                    print(f"  - ({item['item_id']}) {item['title']} [Collections: {item['collections']}]")
            
            # Print flag changes if any
            if result['flags_added_details']:
                print(f"\nAdded missing_pdf flags to:")
                for item in result['flags_added_details']:
                    print(f"  - {item['title']} [Collections: {item['collections']}]")
            
            if result['flags_removed_details']:
                print(f"\nRemoved missing_pdf flags from:")
                for item in result['flags_removed_details']:
                    print(f"  - {item['title']} [Collections: {item['collections']}]")
            
            # Print errors if any
            if result['error_details']:
                print(f"\nErrors encountered:")
                for error in result['error_details']:
                    print(f"  - {error}")
        else:
            # Handle other database-level tasks here in the future
            print(f"Database-level task {args.task} not yet implemented")
            sys.exit(1)
            
    except Exception as e:
        logging.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main_cli()