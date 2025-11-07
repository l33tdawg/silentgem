"""
Embedding Service for generating semantic vector embeddings
"""

import asyncio
from typing import List, Optional, Union
import numpy as np
from loguru import logger
from pathlib import Path

# Singleton instance
_embedding_service = None


class EmbeddingService:
    """
    Service for generating semantic embeddings using sentence-transformers
    
    Uses a lightweight but effective model (all-MiniLM-L6-v2):
    - Only 80MB
    - 384-dimensional vectors
    - Good balance of speed and quality
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_dir: Optional[str] = None):
        """
        Initialize the embedding service
        
        Args:
            model_name: Name of the sentence-transformers model
            cache_dir: Directory to cache the model (optional)
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.model = None
        self._initialized = False
        
    def _lazy_load_model(self):
        """Lazy load the model only when first needed"""
        if self._initialized:
            return
            
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name, cache_folder=self.cache_dir)
            self._initialized = True
            logger.info(f"Embedding model loaded successfully (dimension: {self.model.get_sentence_embedding_dimension()})")
            
        except ImportError:
            logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    async def embed(self, text: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """
        Generate embeddings for text(s)
        
        Args:
            text: Single text string or list of strings
            
        Returns:
            numpy array(s) of embeddings
        """
        # Lazy load on first use
        if not self._initialized:
            self._lazy_load_model()
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def _encode():
            if isinstance(text, str):
                # Single text
                embedding = self.model.encode(text, show_progress_bar=False)
                return embedding
            else:
                # Batch of texts
                embeddings = self.model.encode(text, show_progress_bar=False, batch_size=32)
                return embeddings
        
        return await loop.run_in_executor(None, _encode)
    
    def embed_sync(self, text: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """
        Synchronous version of embed() for non-async contexts
        
        Args:
            text: Single text string or list of strings
            
        Returns:
            numpy array(s) of embeddings
        """
        if not self._initialized:
            self._lazy_load_model()
        
        if isinstance(text, str):
            return self.model.encode(text, show_progress_bar=False)
        else:
            return self.model.encode(text, show_progress_bar=False, batch_size=32)
    
    def cosine_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score (0-1, higher = more similar)
        """
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    @property
    def embedding_dim(self) -> int:
        """Get the dimensionality of embeddings"""
        if not self._initialized:
            self._lazy_load_model()
        return self.model.get_sentence_embedding_dimension()


def get_embedding_service(
    model_name: str = "all-MiniLM-L6-v2",
    cache_dir: Optional[str] = None
) -> EmbeddingService:
    """
    Get singleton instance of EmbeddingService
    
    Args:
        model_name: Name of the sentence-transformers model
        cache_dir: Directory to cache the model
        
    Returns:
        EmbeddingService instance
    """
    global _embedding_service
    
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name=model_name, cache_dir=cache_dir)
    
    return _embedding_service

