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
        'object_type',
        choices=['item', 'collection'],
        help='Type of object to process (item or collection)'
    )
    
    parser.add_argument(
        'task',
        choices=['llm_summary', 'key_references'],
        help='Task to perform'
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
        '--query',
        help='Search query to find items'
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
            if args.unfiled:
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
                print(f"Error: --collection-path or --unfiled required for collection {args.task} task")
                sys.exit(1)
                
        else:
            print(f"Unknown object type: {args.object_type}")
            sys.exit(1)
            
    except Exception as e:
        logging.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main_cli()