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
        '--config', 
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--task',
        choices=['analyze_item'],
        required=True,
        help='Task to perform'
    )
    
    parser.add_argument(
        '--item-id',
        help='Zotero item ID to analyze'
    )
    
    parser.add_argument(
        '--collection-id',
        help='Zotero collection ID to process'
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
        if args.task == 'analyze_item':
            if not args.item_id and not args.query:
                print("Error: --item-id or --query required for analyze_item task")
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
            
            # Analyze the item
            result = tasks.analyze_item(zot, item_id, config)
                
        else:
            print(f"Unknown task: {args.task}")
            sys.exit(1)
            
    except Exception as e:
        logging.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main_cli()