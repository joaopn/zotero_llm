#!/usr/bin/env python3
"""
Zotero LLM QA Session - Interactive Q&A with research papers

This script provides an interactive terminal interface to:
1. Search for papers by title
2. Load the full text
3. Have a conversation with an LLM about the paper
4. Optionally save the conversation as a Zotero note
"""

import argparse
import sys
import logging
import signal
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from zotero_llm import main, llm

# Terminal color codes
COLOR_USER = '\033[92m'      # Bright green
COLOR_ASSISTANT = '\033[96m' # Bright cyan
COLOR_RESET = '\033[0m'      # Reset to default


class QASession:
    """Manages an interactive Q&A session with a research paper."""
    
    def __init__(self, zot, config: Dict[str, Any], verbose: bool = False):
        self.zot = zot
        self.config = config
        self.conversation_history = []
        self.current_item = None
        self.current_fulltext = None
        self.interrupted = False
        self.verbose = verbose
        
        # Set up Ctrl+C handler
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully."""
        self.interrupted = True
        print("\n\n[Conversation ended]")
        raise KeyboardInterrupt
    
    def search_papers_by_title(self, title_query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for papers by title with fuzzy matching.
        
        Args:
            title_query: Title search string
            limit: Maximum number of results
            
        Returns:
            List of matching items sorted by relevance
        """
        logging.info(f"Searching for papers matching: '{title_query}'")
        
        # Search using Zotero API
        items = main.search_items(self.zot, title_query, limit=50)
        
        # Filter out attachments and notes
        items = [item for item in items 
                if item.get('data', {}).get('itemType') not in ['attachment', 'note']]
        
        # Score items by title similarity
        scored_items = []
        for item in items:
            title = item.get('data', {}).get('title', '')
            score = self._similarity_score(title_query.lower(), title.lower())
            scored_items.append((score, item))
        
        # Sort by score (highest first) and limit results
        scored_items.sort(reverse=True, key=lambda x: x[0])
        return [item for score, item in scored_items[:limit]]
    
    def _similarity_score(self, query: str, text: str) -> float:
        """Calculate similarity score between query and text."""
        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, query, text).ratio()
    
    def display_search_results(self, items: List[Dict[str, Any]]) -> None:
        """Display search results in a numbered list."""
        print("\n" + "="*80)
        print("SEARCH RESULTS:")
        print("="*80)
        
        for idx, item in enumerate(items, 1):
            data = item.get('data', {})
            title = data.get('title', 'Unknown Title')
            authors = data.get('creators', [])
            author_names = [f"{c.get('lastName', '')}" for c in authors[:3]]
            author_str = ', '.join(author_names)
            if len(authors) > 3:
                author_str += ' et al.'
            
            year = data.get('date', '')[:4] if data.get('date') else ''
            
            print(f"\n{idx}. {title}")
            print(f"   Authors: {author_str}")
            if year:
                print(f"   Year: {year}")
        
        print("\n" + "="*80)
    
    def select_paper(self, items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Prompt user to select a paper from search results.
        
        Args:
            items: List of paper items
            
        Returns:
            Selected item or None if cancelled
        """
        while True:
            try:
                choice = input("\nEnter paper number (or 'q' to quit): ").strip()
                
                if choice.lower() == 'q':
                    return None
                
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    return items[idx]
                else:
                    print(f"Please enter a number between 1 and {len(items)}")
            except ValueError:
                print("Please enter a valid number or 'q' to quit")
            except KeyboardInterrupt:
                return None
    
    def load_paper(self, item: Dict[str, Any]) -> bool:
        """
        Load paper metadata and fulltext.
        
        Args:
            item: Zotero item
            
        Returns:
            True if successful, False otherwise
        """
        self.current_item = item
        item_id = item.get('key')
        data = item.get('data', {})
        title = data.get('title', 'Unknown Title')
        
        print(f"\nLoading paper: {title}")
        print("Retrieving full text...")
        
        # Get fulltext
        fulltext = main.get_item_fulltext(self.zot, item_id)
        
        if not fulltext:
            print("\n⚠️  Warning: Could not retrieve full text for this paper.")
            print("The Q&A will be based on metadata and abstract only.")
            fulltext = ""
        else:
            print(f"✓ Full text loaded ({len(fulltext):,} characters)")
        
        # Set fulltext BEFORE estimating tokens
        self.current_fulltext = fulltext
        
        # Estimate token count and cost (only if we have fulltext)
        if fulltext:
            self._print_token_estimate(fulltext)
        
        return True
    
    def _print_token_estimate(self, fulltext: str) -> None:
        """
        Print token estimate and warning about context length and cost.
        
        Args:
            fulltext: The full text content
        """
        # Build the full context that will be sent
        paper_context = self.get_paper_context()
        
        # Estimate word count
        word_count = len(paper_context.split())
        token_count = word_count * 0.75
        
        print(f"Paper word count: {word_count:,} words, ~{int(token_count):,} tokens")
    
    def get_paper_context(self) -> str:
        """Build context string from paper metadata and fulltext."""
        data = self.current_item.get('data', {})
        
        title = data.get('title', 'Unknown Title')
        authors = data.get('creators', [])
        author_names = [f"{c.get('firstName', '')} {c.get('lastName', '')}" for c in authors]
        abstract = data.get('abstractNote', '')
        
        context = f"""Research Paper Details:
Title: {title}
Authors: {', '.join(author_names)}
Abstract: {abstract}

Full Text:
{self.current_fulltext}
"""
        return context
    
    def chat_loop(self) -> None:
        """Main chat conversation loop."""
        # Load prompts
        prompts_file = self.config.get('prompts_file', 'prompts.yaml')
        prompts_config = main.load_prompts(prompts_file)
        
        # Get QA system prompt
        qa_config = prompts_config.get('tasks', {}).get('qa_session', {})
        system_prompt = qa_config.get('system_prompt', 
            'You are an AI assistant helping to answer questions about a research paper.')
        
        # Build initial context
        paper_context = self.get_paper_context()
        
        data = self.current_item.get('data', {})
        title = data.get('title', 'Unknown Title')
        
        print("\n" + "="*80)
        print(f"Q&A SESSION: {title}")
        print("="*80)
        print("\nYou can now ask questions about this paper, context will be loaded on first question.")
        print("Press Ctrl+C to end the conversation.\n")
        
        # Silence logging during chat mode to avoid mixing with LLM output
        original_log_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.CRITICAL)
        
        try:
            while True:
                # Get user question
                try:
                    question = input(f"\n{COLOR_USER}You:{COLOR_RESET} ").strip()
                except EOFError:
                    break
                
                if not question:
                    continue
                
                # Build prompt with context and conversation history
                conversation_text = self._format_conversation_history()
                
                full_prompt = f"""{system_prompt}

{paper_context}

Previous conversation:
{conversation_text}

User question: {question}

Please provide a helpful answer based on the paper content above."""
                
                # Call LLM
                print(f"\n{COLOR_ASSISTANT}Assistant:{COLOR_RESET} [thinking...]", end='', flush=True)
                try:
                    response = llm.call_llm(full_prompt, self.config)
                    # Clear the "thinking" message and print response
                    print("\r" + " " * 40 + "\r", end='', flush=True)  # Clear the line
                    print(f"{COLOR_ASSISTANT}Assistant:{COLOR_RESET} ", end='', flush=True)
                    print(response)
                    
                    # Save to conversation history
                    self.conversation_history.append({
                        'question': question,
                        'answer': response
                    })
                    
                except Exception as e:
                    print(f"\n\n⚠️  Error calling LLM: {e}")
                    
        except KeyboardInterrupt:
            # Ctrl+C was pressed
            pass
        finally:
            # Restore original logging level
            logging.getLogger().setLevel(original_log_level)
    
    def _format_conversation_history(self) -> str:
        """Format conversation history for context."""
        if not self.conversation_history:
            return "(No previous conversation)"
        
        formatted = []
        for entry in self.conversation_history:
            formatted.append(f"Q: {entry['question']}")
            formatted.append(f"A: {entry['answer']}")
        
        return "\n\n".join(formatted)
    
    def save_conversation_prompt(self) -> bool:
        """
        Prompt user to save conversation as a Zotero note.
        
        Returns:
            True if saved, False otherwise
        """
        if not self.conversation_history:
            print("\nNo conversation to save.")
            return False
        
        print("\n" + "="*80)
        while True:
            try:
                choice = input("Save this conversation as a note? (y/n): ").strip().lower()
                
                if choice == 'y':
                    return self._save_conversation_to_note()
                elif choice == 'n':
                    print("Conversation not saved.")
                    return False
                else:
                    print("Please enter 'y' or 'n'")
            except (KeyboardInterrupt, EOFError):
                print("\nConversation not saved.")
                return False
    
    def _save_conversation_to_note(self) -> bool:
        """Save conversation by appending to existing LLM QA note or creating new one."""
        try:
            item_id = self.current_item.get('key')
            data = self.current_item.get('data', {})
            
            # Get model name
            model_name = self.config.get('llm', {}).get('model', 'Unknown Model')
            
            # Format new conversation session in chat style
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Get first question for the header
            first_question = self.conversation_history[0]['question'] if self.conversation_history else "Q&A Session"
            
            # Format session with model info (for appending to existing notes)
            session_content_with_model = f"<h3>Q&A Session - {timestamp}</h3>\n"
            session_content_with_model += f"<h3>Q: {first_question}</h3>\n"
            session_content_with_model += "<pre>\n"
            
            for entry in self.conversation_history:
                session_content_with_model += f"User: {entry['question']}\n\n"
                session_content_with_model += f"LLM: {entry['answer']}\n\n"
            
            session_content_with_model += f"\nModel: {model_name}\n"
            session_content_with_model += "</pre>\n"
            
            # Format session without model info (for new notes - create_note_annotation adds it)
            session_content_no_model = f"<h3>Q&A Session - {timestamp}</h3>\n"
            session_content_no_model += f"<h3>Q: {first_question}</h3>\n"
            session_content_no_model += "<pre>\n"
            
            for entry in self.conversation_history:
                session_content_no_model += f"User: {entry['question']}\n\n"
                session_content_no_model += f"LLM: {entry['answer']}\n\n"
            
            session_content_no_model += f"\nModel: {model_name}\n"
            session_content_no_model += "</pre>\n"
            
            # Check if LLM QA note already exists
            item = self.zot.item(item_id)
            parent_item_id = item_id
            
            # If this is an attachment, find its parent item
            if item['data'].get('itemType') == 'attachment':
                parent_key = item['data'].get('parentItem')
                if parent_key:
                    parent_item_id = parent_key
                else:
                    parent_item_id = None
            
            # Look for existing LLM QA note
            existing_note = None
            if parent_item_id:
                try:
                    existing_items = self.zot.children(parent_item_id)
                    existing_notes = [item for item in existing_items if item['data'].get('itemType') == 'note']
                    
                    for note in existing_notes:
                        note_content = note['data'].get('note', '')
                        # Check if this is an LLM QA note
                        if '<h2>LLM QA</h2>' in note_content:
                            existing_note = note
                            break
                except Exception as e:
                    logging.warning(f"Could not check existing notes: {e}")
            
            if existing_note:
                # Append to existing note (use version WITH model info)
                existing_content = existing_note['data']['note']
                
                # Remove closing tags if present and append new session
                # The content should be in format: <h2>LLM QA</h2><p><strong>Model:</strong> ...</p>...
                new_content = existing_content + "\n" + session_content_with_model
                
                existing_note['data']['note'] = new_content
                result = self.zot.update_item(existing_note)
                
                if result:
                    print("✓ Conversation appended to existing 'LLM QA' note")
                    return True
                else:
                    print("⚠️  Failed to update note")
                    return False
            else:
                # Create new note (use version WITHOUT model info - create_note_annotation adds it)
                success = main.create_note_annotation(
                    self.zot, 
                    item_id, 
                    session_content_no_model, 
                    model_name, 
                    "LLM QA"
                )
                
                if success:
                    print("✓ Conversation saved as new 'LLM QA' note")
                    return True
                else:
                    print("⚠️  Failed to save conversation")
                    return False
                
        except Exception as e:
            print(f"⚠️  Error saving conversation: {e}")
            logging.error(f"Failed to save conversation: {e}")
            return False
    
    def _markdown_to_html(self, markdown: str) -> str:
        """
        Convert markdown to simple HTML for Zotero notes.
        Basic conversion without external dependencies.
        """
        import re
        
        html = markdown
        
        # Headers
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        
        # Italic
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # Paragraphs (split by double newlines)
        paragraphs = html.split('\n\n')
        formatted_paragraphs = []
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith('<h'):
                formatted_paragraphs.append(f'<p>{p}</p>')
            else:
                formatted_paragraphs.append(p)
        
        html = '\n'.join(formatted_paragraphs)
        
        # Single newlines to <br>
        html = re.sub(r'(?<!</p>)\n(?!<)', '<br>', html)
        
        return html
    
    def run(self) -> None:
        """Run the complete QA session workflow."""
        # Silence INFO logging if not verbose
        if not self.verbose:
            logging.getLogger().setLevel(logging.WARNING)
        
        print("\n" + "="*80)
        print("ZOTERO LLM Q&A SESSION")
        print("="*80)
        
        # Step 1: Get title query from user
        try:
            title_query = input("\nEnter paper title to search: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            return
        
        if not title_query:
            print("No title provided. Exiting...")
            return
        
        # Step 2: Search for papers
        items = self.search_papers_by_title(title_query)
        
        if not items:
            print(f"\nNo papers found matching '{title_query}'")
            return
        
        # Step 3: Display results and let user select
        self.display_search_results(items)
        selected_item = self.select_paper(items)
        
        if not selected_item:
            print("\nNo paper selected. Exiting...")
            return
        
        # Step 4: Load paper
        if not self.load_paper(selected_item):
            print("\nFailed to load paper. Exiting...")
            return
        
        # Step 5: Start chat loop
        self.chat_loop()
        
        # Step 6: Prompt to save conversation
        self.save_conversation_prompt()
        
        print("\n" + "="*80)
        print("Session ended. Goodbye!")
        print("="*80 + "\n")


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Zotero LLM Q&A Session - Interactive chat with research papers"
    )
    
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
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
        
        # Create and run QA session
        session = QASession(zot, config, verbose=args.verbose)
        session.run()
        
    except Exception as e:
        logging.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main_cli()

