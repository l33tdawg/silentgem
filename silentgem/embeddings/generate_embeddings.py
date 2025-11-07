#!/usr/bin/env python3
"""
Generate embeddings for existing messages in the database
"""

import asyncio
import numpy as np
from loguru import logger
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from silentgem.database.message_store import get_message_store
from silentgem.embeddings.embedding_service import get_embedding_service


async def generate_embeddings_batch(batch_size: int = 50):
    """
    Generate embeddings for messages in batches
    
    Args:
        batch_size: Number of messages to process in each batch
    """
    message_store = get_message_store()
    embedding_service = get_embedding_service()
    
    # Get total counts
    cursor = message_store.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE is_media = 0 AND content IS NOT NULL AND LENGTH(content) > 10")
    total_messages = cursor.fetchone()[0]
    
    existing_embeddings = message_store.count_embeddings()
    
    logger.info(f"Total messages: {total_messages}")
    logger.info(f"Existing embeddings: {existing_embeddings}")
    logger.info(f"Messages without embeddings: {total_messages - existing_embeddings}")
    
    if existing_embeddings >= total_messages:
        logger.info("✅ All messages already have embeddings!")
        return
    
    # Process in batches
    processed = 0
    total_to_process = total_messages - existing_embeddings
    
    while True:
        # Get next batch of messages without embeddings
        messages = message_store.get_messages_without_embeddings(limit=batch_size)
        
        if not messages:
            logger.info("✅ All messages have been processed!")
            break
        
        logger.info(f"Processing batch of {len(messages)} messages...")
        
        # Extract text content for batch embedding
        texts = []
        message_ids = []
        
        for msg in messages:
            content = msg.get('content', '')
            if content and len(content) > 10:  # Skip very short messages
                texts.append(content)
                message_ids.append(msg['id'])
        
        if not texts:
            logger.warning("No valid text content in this batch")
            continue
        
        # Generate embeddings for the batch
        try:
            logger.info(f"Generating {len(texts)} embeddings...")
            embeddings = await embedding_service.embed(texts)
            
            # Store embeddings
            for msg_id, embedding in zip(message_ids, embeddings):
                # Convert numpy array to bytes
                embedding_bytes = embedding.tobytes()
                
                # Store in database
                message_store.store_embedding(
                    message_id=msg_id,
                    embedding=embedding_bytes,
                    model='all-MiniLM-L6-v2'
                )
                
                processed += 1
            
            logger.info(f"✅ Processed {processed}/{total_to_process} messages ({processed/total_to_process*100:.1f}%)")
            
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            continue
    
    logger.info(f"🎉 Finished! Generated {processed} embeddings")


async def verify_embeddings():
    """Verify that embeddings are stored correctly"""
    message_store = get_message_store()
    embedding_service = get_embedding_service()
    
    # Get a sample embedding
    embeddings = message_store.get_all_embeddings(limit=5)
    
    if not embeddings:
        logger.warning("No embeddings found!")
        return
    
    logger.info(f"\n📊 Sample embeddings:")
    
    for emb in embeddings:
        # Convert bytes back to numpy array
        embedding_bytes = emb['embedding']
        embedding_array = np.frombuffer(embedding_bytes, dtype=np.float32)
        
        logger.info(f"\nMessage ID: {emb['message_id']}")
        logger.info(f"Content: {emb['content'][:100]}...")
        logger.info(f"Embedding shape: {embedding_array.shape}")
        logger.info(f"Embedding norm: {np.linalg.norm(embedding_array):.4f}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")
    
    import argparse
    parser = argparse.ArgumentParser(description="Generate embeddings for messages")
    parser.add_argument('--verify', action='store_true', help='Verify existing embeddings')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for processing')
    
    args = parser.parse_args()
    
    if args.verify:
        asyncio.run(verify_embeddings())
    else:
        asyncio.run(generate_embeddings_batch(batch_size=args.batch_size))

