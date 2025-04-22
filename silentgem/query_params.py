"""
Query parameters for search operations in the Chat Insights bot.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta


class ParamCompatibility(Enum):
    """Compatibility level for search parameters"""
    COMPATIBLE = "compatible"
    PARTIAL = "partial"
    INCOMPATIBLE = "incompatible"


@dataclass
class QueryParams:
    """Parameters for search queries"""
    query: str
    limit: int = 20
    offset: int = 0
    chat_id: Optional[str] = None
    user_id: Optional[str] = None
    time_period: Optional[str] = None
    strategies: List[str] = None
    sender: Optional[str] = None
    
    def __post_init__(self):
        if self.strategies is None:
            self.strategies = ["direct", "semantic"]
    
    def get_time_range(self) -> Optional[tuple[datetime, datetime]]:
        """
        Convert time_period to a datetime range
        
        Returns:
            Optional tuple of (start_time, end_time)
        """
        if not self.time_period:
            return None
            
        now = datetime.now()
        
        if self.time_period == "today":
            # Today (midnight to now)
            start = datetime(now.year, now.month, now.day, 0, 0, 0)
            return (start, now)
            
        elif self.time_period == "yesterday":
            # Yesterday (midnight to midnight)
            yesterday = now - timedelta(days=1)
            start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
            end = datetime(now.year, now.month, now.day, 0, 0, 0)
            return (start, end)
            
        elif self.time_period == "week":
            # Last 7 days
            start = now - timedelta(days=7)
            return (start, now)
            
        elif self.time_period == "month":
            # Last 30 days
            start = now - timedelta(days=30)
            return (start, now)
            
        return None
    
    def is_compatible_with(self, other: 'QueryParams') -> ParamCompatibility:
        """
        Check if this query is compatible with another query
        
        Args:
            other: Another QueryParams instance to compare with
            
        Returns:
            ParamCompatibility level
        """
        # Incompatible if searching different chats
        if self.chat_id and other.chat_id and self.chat_id != other.chat_id:
            return ParamCompatibility.INCOMPATIBLE
            
        # Incompatible if searching different users
        if self.user_id and other.user_id and self.user_id != other.user_id:
            return ParamCompatibility.INCOMPATIBLE
            
        # Incompatible if searching different senders
        if self.sender and other.sender and self.sender != other.sender:
            return ParamCompatibility.INCOMPATIBLE
            
        # Check time compatibility
        time_compat = self._check_time_compatibility(other)
        if time_compat == ParamCompatibility.INCOMPATIBLE:
            return ParamCompatibility.INCOMPATIBLE
            
        # If we reach here, at least partially compatible
        if self.query != other.query:
            return ParamCompatibility.PARTIAL
            
        # Fully compatible
        return ParamCompatibility.COMPATIBLE
    
    def _check_time_compatibility(self, other: 'QueryParams') -> ParamCompatibility:
        """
        Check time period compatibility
        
        Args:
            other: Another QueryParams instance
            
        Returns:
            ParamCompatibility level for time periods
        """
        # If either doesn't have a time period, they're compatible
        if not self.time_period or not other.time_period:
            return ParamCompatibility.COMPATIBLE
            
        # If exact match, they're compatible
        if self.time_period == other.time_period:
            return ParamCompatibility.COMPATIBLE
            
        # Check for overlapping time periods
        self_range = self.get_time_range()
        other_range = other.get_time_range()
        
        if not self_range or not other_range:
            return ParamCompatibility.COMPATIBLE
            
        self_start, self_end = self_range
        other_start, other_end = other_range
        
        # Check for no overlap
        if self_end < other_start or self_start > other_end:
            return ParamCompatibility.INCOMPATIBLE
            
        # There is some overlap
        return ParamCompatibility.PARTIAL 