#!/usr/bin/env python3
"""
Background worker for processing embedding backlog

This script can be run independently to generate embeddings for messages
that don't have them yet. It's designed to be lightweight and can be:
- Run as a one-off task
- Scheduled with cron
- Run continuously in the background
"""

import asyncio
import argparse
import time
from loguru import logger

from silentgem.database.message_store import get_message_store


async def process_backlog(batch_size: int = 50, max_messages: int = None, continuous: bool = False, interval: int = 300):
    """
    Process embedding backlog
    
    Args:
        batch_size: Number of messages to process in each batch
        max_messages: Maximum number of messages to process per run (None = all)
        continuous: Whether to run continuously
        interval: Seconds to wait between runs (if continuous)
    """
    message_store = get_message_store()
    
    if continuous:
        logger.info(f"Starting continuous embedding worker (checking every {interval}s)")
        while True:
            try:
                # Check how many messages need embeddings
                pending = message_store.get_messages_without_embeddings(limit=1)
                
                if pending:
                    logger.info("Found messages without embeddings, processing...")
                    processed = await message_store.process_embedding_backlog(
                        batch_size=batch_size,
                        max_messages=max_messages
                    )
                    logger.info(f"Processed {processed} embeddings")
                else:
                    logger.debug("No pending messages, waiting...")
                
                # Wait before next check
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("Stopping continuous worker...")
                break
            except Exception as e:
                logger.error(f"Error in continuous worker: {e}")
                await asyncio.sleep(interval)
    else:
        # One-off processing
        logger.info("Starting one-off embedding processing")
        start_time = time.time()
        
        processed = await message_store.process_embedding_backlog(
            batch_size=batch_size,
            max_messages=max_messages
        )
        
        elapsed = time.time() - start_time
        logger.info(f"Completed: {processed} embeddings generated in {elapsed:.2f}s")
        
        if processed > 0:
            rate = processed / elapsed
            logger.info(f"Processing rate: {rate:.1f} messages/second")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Background worker for generating message embeddings"
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of messages to process in each batch (default: 50)'
    )
    
    parser.add_argument(
        '--max-messages',
        type=int,
        default=None,
        help='Maximum number of messages to process (default: all)'
    )
    
    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Run continuously, checking for new messages periodically'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Seconds to wait between checks in continuous mode (default: 300)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logger.remove()
        logger.add(lambda msg: print(msg, end=''), level="DEBUG")
    
    # Run the worker
    try:
        asyncio.run(process_backlog(
            batch_size=args.batch_size,
            max_messages=args.max_messages,
            continuous=args.continuous,
            interval=args.interval
        ))
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise


if __name__ == "__main__":
    main()

