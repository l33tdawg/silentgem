"""
Bridge to the actual query processor in silentgem.search.query_processor
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from silentgem.search.query_processor import get_query_processor as get_search_query_processor


@dataclass
class QueryInterpretationResult:
    """Results of query interpretation"""
    processed_query: Optional[str] = None
    time_period: Optional[str] = None
    cross_chats: bool = False
    expanded_terms: List[str] = None
    search_strategies: List[str] = None
    sender: Optional[str] = None
    intent: str = "search"
    
    def __post_init__(self):
        if self.expanded_terms is None:
            self.expanded_terms = []
        if self.search_strategies is None:
            self.search_strategies = ["direct", "semantic"]


class QueryProcessor:
    """
    Bridge to the actual query processor in silentgem.search.query_processor
    """
    
    def __init__(self):
        self._search_query_processor = get_search_query_processor()
    
    async def process_query(
        self,
        query: str,
        include_time: bool = True,
        include_inferred_params: bool = True,
        context: Optional[Dict[str, Any]] = None
    ) -> QueryInterpretationResult:
        """
        Process a query and return interpretation results
        
        Args:
            query: The query text
            include_time: Whether to include time period analysis
            include_inferred_params: Whether to include inferred parameters
            context: Optional context from previous conversation
            
        Returns:
            QueryInterpretationResult with processed query and metadata
        """
        try:
            # Get results from the search query processor
            search_result = await self._search_query_processor.process_query(query_text=query)
            
            # Ensure search_result is a dict
            if not search_result or not isinstance(search_result, dict):
                search_result = {"query_text": query}
            
            # Convert to QueryInterpretationResult format
            result = QueryInterpretationResult(
                processed_query=search_result.get("query_text", query),
                time_period=search_result.get("time_period"),
                cross_chats=True,  # Default to searching across all chats
                expanded_terms=search_result.get("expanded_terms", []),
                search_strategies=search_result.get("search_strategies", ["direct", "semantic"]),
                sender=search_result.get("sender"),
                intent=search_result.get("intent", "search")
            )
            
            return result
            
        except Exception as e:
            # If anything goes wrong, return a basic result
            return QueryInterpretationResult(
                processed_query=query,
                time_period=None,
                cross_chats=True,
                expanded_terms=[],
                search_strategies=["direct", "semantic"],
                sender=None,
                intent="search"
            )


def get_query_processor():
    """Get the LLM query processor singleton"""
    return QueryProcessor() 