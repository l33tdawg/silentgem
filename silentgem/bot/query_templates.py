"""
Query Templates Module for SilentGem v1.5

Allows users to save and reuse common search queries as templates.
"""

import json
import os
import time
from typing import Dict, List, Optional
from loguru import logger
from dataclasses import dataclass, field, asdict


@dataclass
class QueryTemplate:
    """Represents a saved query template"""
    id: str
    name: str
    query: str
    description: str = ""
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    use_count: int = 0
    user_id: str = ""
    tags: List[str] = field(default_factory=list)


class QueryTemplateManager:
    """
    Manages saving, loading, and using query templates
    """
    
    def __init__(self, storage_dir: str = "data"):
        """Initialize the query template manager"""
        self.storage_dir = storage_dir
        self.templates_file = os.path.join(storage_dir, "query_templates.json")
        self.templates: Dict[str, QueryTemplate] = {}
        self._load_templates()
    
    def _load_templates(self):
        """Load templates from disk"""
        try:
            if os.path.exists(self.templates_file):
                with open(self.templates_file, 'r') as f:
                    data = json.load(f)
                    
                    for template_id, template_data in data.items():
                        self.templates[template_id] = QueryTemplate(**template_data)
                
                logger.info(f"Loaded {len(self.templates)} query templates")
            else:
                logger.info("No existing query templates found")
        except Exception as e:
            logger.error(f"Error loading query templates: {e}")
            self.templates = {}
    
    def _save_templates(self):
        """Save templates to disk"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(self.storage_dir, exist_ok=True)
            
            # Convert templates to dict
            data = {
                template_id: asdict(template)
                for template_id, template in self.templates.items()
            }
            
            # Write to file
            with open(self.templates_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved {len(self.templates)} query templates")
        except Exception as e:
            logger.error(f"Error saving query templates: {e}")
    
    def create_template(
        self,
        name: str,
        query: str,
        user_id: str,
        description: str = "",
        tags: Optional[List[str]] = None
    ) -> QueryTemplate:
        """
        Create a new query template
        
        Args:
            name: Template name
            query: The query text
            user_id: User ID who created the template
            description: Optional description
            tags: Optional tags for categorization
            
        Returns:
            Created QueryTemplate
        """
        # Generate template ID from name
        template_id = self._generate_template_id(name, user_id)
        
        template = QueryTemplate(
            id=template_id,
            name=name,
            query=query,
            description=description,
            user_id=user_id,
            tags=tags or []
        )
        
        self.templates[template_id] = template
        self._save_templates()
        
        logger.info(f"Created template '{name}' (ID: {template_id})")
        return template
    
    def get_template(self, template_id: str) -> Optional[QueryTemplate]:
        """Get a template by ID"""
        return self.templates.get(template_id)
    
    def get_template_by_name(self, name: str, user_id: str) -> Optional[QueryTemplate]:
        """Get a template by name for a specific user"""
        template_id = self._generate_template_id(name, user_id)
        return self.templates.get(template_id)
    
    def list_templates(self, user_id: Optional[str] = None, tags: Optional[List[str]] = None) -> List[QueryTemplate]:
        """
        List templates, optionally filtered by user and/or tags
        
        Args:
            user_id: Optional user ID to filter by
            tags: Optional tags to filter by
            
        Returns:
            List of matching templates
        """
        templates = list(self.templates.values())
        
        # Filter by user ID
        if user_id:
            templates = [t for t in templates if t.user_id == user_id]
        
        # Filter by tags
        if tags:
            templates = [
                t for t in templates
                if any(tag in t.tags for tag in tags)
            ]
        
        # Sort by last used (most recent first)
        templates.sort(key=lambda t: t.last_used, reverse=True)
        
        return templates
    
    def use_template(self, template_id: str) -> Optional[str]:
        """
        Use a template and return its query
        
        Updates usage statistics and returns the query string.
        
        Args:
            template_id: Template ID to use
            
        Returns:
            Query string or None if template not found
        """
        template = self.templates.get(template_id)
        
        if not template:
            return None
        
        # Update usage statistics
        template.last_used = time.time()
        template.use_count += 1
        
        self._save_templates()
        
        logger.info(f"Using template '{template.name}' (used {template.use_count} times)")
        return template.query
    
    def delete_template(self, template_id: str) -> bool:
        """
        Delete a template
        
        Args:
            template_id: Template ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        if template_id in self.templates:
            template_name = self.templates[template_id].name
            del self.templates[template_id]
            self._save_templates()
            logger.info(f"Deleted template '{template_name}' (ID: {template_id})")
            return True
        
        return False
    
    def update_template(
        self,
        template_id: str,
        name: Optional[str] = None,
        query: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[QueryTemplate]:
        """
        Update a template
        
        Args:
            template_id: Template ID to update
            name: New name (optional)
            query: New query (optional)
            description: New description (optional)
            tags: New tags (optional)
            
        Returns:
            Updated template or None if not found
        """
        template = self.templates.get(template_id)
        
        if not template:
            return None
        
        if name is not None:
            template.name = name
        if query is not None:
            template.query = query
        if description is not None:
            template.description = description
        if tags is not None:
            template.tags = tags
        
        self._save_templates()
        
        logger.info(f"Updated template '{template.name}' (ID: {template_id})")
        return template
    
    def _generate_template_id(self, name: str, user_id: str) -> str:
        """Generate a unique template ID from name and user ID"""
        # Create a slug from the name
        import re
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        return f"{user_id}_{slug}"
    
    def get_popular_templates(self, user_id: str, limit: int = 5) -> List[QueryTemplate]:
        """
        Get most frequently used templates for a user
        
        Args:
            user_id: User ID
            limit: Maximum number of templates to return
            
        Returns:
            List of templates sorted by use count
        """
        user_templates = [t for t in self.templates.values() if t.user_id == user_id]
        user_templates.sort(key=lambda t: t.use_count, reverse=True)
        return user_templates[:limit]
    
    def search_templates(self, search_term: str, user_id: Optional[str] = None) -> List[QueryTemplate]:
        """
        Search templates by name or description
        
        Args:
            search_term: Term to search for
            user_id: Optional user ID to filter by
            
        Returns:
            List of matching templates
        """
        search_lower = search_term.lower()
        templates = list(self.templates.values())
        
        # Filter by user if specified
        if user_id:
            templates = [t for t in templates if t.user_id == user_id]
        
        # Search in name and description
        matching = [
            t for t in templates
            if search_lower in t.name.lower() or search_lower in t.description.lower()
        ]
        
        return matching


# Singleton instance
_query_template_manager = None

def get_query_template_manager() -> QueryTemplateManager:
    """Get the query template manager singleton"""
    global _query_template_manager
    if _query_template_manager is None:
        _query_template_manager = QueryTemplateManager()
    return _query_template_manager

