"""
Unit tests for query_templates.py

Tests the QueryTemplateManager functionality including:
- Creating templates
- Retrieving templates
- Updating templates
- Deleting templates
- Searching templates
- Template usage tracking
"""

import pytest
import os
import json
import tempfile
import shutil
from silentgem.bot.query_templates import QueryTemplateManager, QueryTemplate


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for testing"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def template_manager(temp_storage_dir):
    """Create a fresh QueryTemplateManager for each test"""
    return QueryTemplateManager(storage_dir=temp_storage_dir)


class TestQueryTemplateCreation:
    """Tests for creating query templates"""
    
    def test_create_template_basic(self, template_manager):
        """Test creating a basic template"""
        template = template_manager.create_template(
            name="Test Template",
            query="What happened today?",
            user_id="user123"
        )
        
        assert template is not None
        assert template.name == "Test Template"
        assert template.query == "What happened today?"
        assert template.user_id == "user123"
        assert template.use_count == 0
        assert template.id == "user123_test_template"
    
    def test_create_template_with_description(self, template_manager):
        """Test creating a template with description and tags"""
        template = template_manager.create_template(
            name="Daily Brief",
            query="Summary of today's events",
            user_id="user456",
            description="Get daily news summary",
            tags=["daily", "news", "summary"]
        )
        
        assert template.description == "Get daily news summary"
        assert template.tags == ["daily", "news", "summary"]
    
    def test_create_template_persists_to_disk(self, template_manager, temp_storage_dir):
        """Test that templates are saved to disk"""
        template_manager.create_template(
            name="Persistent Template",
            query="Test query",
            user_id="user789"
        )
        
        # Check file exists
        templates_file = os.path.join(temp_storage_dir, "query_templates.json")
        assert os.path.exists(templates_file)
        
        # Check content
        with open(templates_file, 'r') as f:
            data = json.load(f)
            assert "user789_persistent_template" in data


class TestQueryTemplateRetrieval:
    """Tests for retrieving query templates"""
    
    def test_get_template_by_id(self, template_manager):
        """Test retrieving a template by ID"""
        created = template_manager.create_template(
            name="Get Test",
            query="Test query",
            user_id="user123"
        )
        
        retrieved = template_manager.get_template(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == created.name
    
    def test_get_template_by_name(self, template_manager):
        """Test retrieving a template by name and user"""
        template_manager.create_template(
            name="Named Template",
            query="Test query",
            user_id="user123"
        )
        
        retrieved = template_manager.get_template_by_name("Named Template", "user123")
        
        assert retrieved is not None
        assert retrieved.name == "Named Template"
    
    def test_get_nonexistent_template(self, template_manager):
        """Test retrieving a template that doesn't exist"""
        result = template_manager.get_template("nonexistent_id")
        assert result is None
    
    def test_list_templates_empty(self, template_manager):
        """Test listing templates when none exist"""
        templates = template_manager.list_templates()
        assert templates == []
    
    def test_list_templates_filter_by_user(self, template_manager):
        """Test listing templates filtered by user ID"""
        template_manager.create_template("Template 1", "Query 1", "user1")
        template_manager.create_template("Template 2", "Query 2", "user1")
        template_manager.create_template("Template 3", "Query 3", "user2")
        
        user1_templates = template_manager.list_templates(user_id="user1")
        
        assert len(user1_templates) == 2
        assert all(t.user_id == "user1" for t in user1_templates)
    
    def test_list_templates_filter_by_tags(self, template_manager):
        """Test listing templates filtered by tags"""
        template_manager.create_template("Template 1", "Q1", "user1", tags=["daily"])
        template_manager.create_template("Template 2", "Q2", "user1", tags=["weekly"])
        template_manager.create_template("Template 3", "Q3", "user1", tags=["daily", "summary"])
        
        daily_templates = template_manager.list_templates(tags=["daily"])
        
        assert len(daily_templates) == 2
        assert all("daily" in t.tags for t in daily_templates)


class TestQueryTemplateUsage:
    """Tests for using query templates"""
    
    def test_use_template(self, template_manager):
        """Test using a template returns the query"""
        template = template_manager.create_template(
            name="Usage Test",
            query="What is the weather?",
            user_id="user123"
        )
        
        query = template_manager.use_template(template.id)
        
        assert query == "What is the weather?"
    
    def test_use_template_increments_count(self, template_manager):
        """Test that using a template increments use count"""
        template = template_manager.create_template(
            name="Counter Test",
            query="Test query",
            user_id="user123"
        )
        
        initial_count = template.use_count
        template_manager.use_template(template.id)
        
        # Get fresh copy from manager
        updated = template_manager.get_template(template.id)
        assert updated.use_count == initial_count + 1
    
    def test_use_template_updates_last_used(self, template_manager):
        """Test that using a template updates last_used timestamp"""
        import time
        
        template = template_manager.create_template(
            name="Timestamp Test",
            query="Test query",
            user_id="user123"
        )
        
        initial_time = template.last_used
        time.sleep(0.1)  # Small delay
        
        template_manager.use_template(template.id)
        
        updated = template_manager.get_template(template.id)
        assert updated.last_used > initial_time
    
    def test_use_nonexistent_template(self, template_manager):
        """Test using a template that doesn't exist"""
        result = template_manager.use_template("nonexistent_id")
        assert result is None
    
    def test_get_popular_templates(self, template_manager):
        """Test getting most popular templates"""
        t1 = template_manager.create_template("Template 1", "Q1", "user1")
        t2 = template_manager.create_template("Template 2", "Q2", "user1")
        t3 = template_manager.create_template("Template 3", "Q3", "user1")
        
        # Use templates different numbers of times
        template_manager.use_template(t1.id)
        template_manager.use_template(t2.id)
        template_manager.use_template(t2.id)
        template_manager.use_template(t3.id)
        template_manager.use_template(t3.id)
        template_manager.use_template(t3.id)
        
        popular = template_manager.get_popular_templates("user1", limit=2)
        
        assert len(popular) == 2
        assert popular[0].id == t3.id  # Most used (3 times)
        assert popular[1].id == t2.id  # Second most (2 times)


class TestQueryTemplateUpdate:
    """Tests for updating query templates"""
    
    def test_update_template_name(self, template_manager):
        """Test updating a template's name"""
        template = template_manager.create_template(
            name="Old Name",
            query="Test query",
            user_id="user123"
        )
        
        updated = template_manager.update_template(
            template.id,
            name="New Name"
        )
        
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.query == "Test query"  # Unchanged
    
    def test_update_template_query(self, template_manager):
        """Test updating a template's query"""
        template = template_manager.create_template(
            name="Test",
            query="Old query",
            user_id="user123"
        )
        
        updated = template_manager.update_template(
            template.id,
            query="New query"
        )
        
        assert updated.query == "New query"
    
    def test_update_template_tags(self, template_manager):
        """Test updating a template's tags"""
        template = template_manager.create_template(
            name="Test",
            query="Query",
            user_id="user123",
            tags=["old"]
        )
        
        updated = template_manager.update_template(
            template.id,
            tags=["new", "updated"]
        )
        
        assert updated.tags == ["new", "updated"]
    
    def test_update_nonexistent_template(self, template_manager):
        """Test updating a template that doesn't exist"""
        result = template_manager.update_template(
            "nonexistent_id",
            name="New Name"
        )
        assert result is None


class TestQueryTemplateDeletion:
    """Tests for deleting query templates"""
    
    def test_delete_template(self, template_manager):
        """Test deleting a template"""
        template = template_manager.create_template(
            name="To Delete",
            query="Test query",
            user_id="user123"
        )
        
        success = template_manager.delete_template(template.id)
        
        assert success is True
        assert template_manager.get_template(template.id) is None
    
    def test_delete_nonexistent_template(self, template_manager):
        """Test deleting a template that doesn't exist"""
        success = template_manager.delete_template("nonexistent_id")
        assert success is False
    
    def test_delete_template_persists(self, template_manager, temp_storage_dir):
        """Test that deletion is persisted to disk"""
        template = template_manager.create_template(
            name="To Delete",
            query="Test query",
            user_id="user123"
        )
        
        template_manager.delete_template(template.id)
        
        # Create new manager to load from disk
        new_manager = QueryTemplateManager(storage_dir=temp_storage_dir)
        assert new_manager.get_template(template.id) is None


class TestQueryTemplateSearch:
    """Tests for searching query templates"""
    
    def test_search_templates_by_name(self, template_manager):
        """Test searching templates by name"""
        template_manager.create_template("Daily News", "News query", "user1")
        template_manager.create_template("Weekly Report", "Report query", "user1")
        template_manager.create_template("Daily Summary", "Summary query", "user1")
        
        results = template_manager.search_templates("daily", user_id="user1")
        
        assert len(results) == 2
        assert all("daily" in t.name.lower() for t in results)
    
    def test_search_templates_by_description(self, template_manager):
        """Test searching templates by description"""
        template_manager.create_template(
            "Template 1", "Q1", "user1", description="Get weather updates"
        )
        template_manager.create_template(
            "Template 2", "Q2", "user1", description="Get news updates"
        )
        template_manager.create_template(
            "Template 3", "Q3", "user1", description="Get stock prices"
        )
        
        results = template_manager.search_templates("updates", user_id="user1")
        
        assert len(results) == 2
    
    def test_search_templates_case_insensitive(self, template_manager):
        """Test that search is case-insensitive"""
        template_manager.create_template("UPPERCASE", "Query", "user1")
        
        results_lower = template_manager.search_templates("uppercase", user_id="user1")
        results_upper = template_manager.search_templates("UPPERCASE", user_id="user1")
        
        assert len(results_lower) == 1
        assert len(results_upper) == 1
    
    def test_search_no_results(self, template_manager):
        """Test search with no matching results"""
        template_manager.create_template("Template", "Query", "user1")
        
        results = template_manager.search_templates("nonexistent", user_id="user1")
        
        assert results == []


class TestQueryTemplateIDGeneration:
    """Tests for template ID generation"""
    
    def test_id_generation_basic(self, template_manager):
        """Test basic ID generation"""
        template = template_manager.create_template(
            "Simple Name",
            "Query",
            "user123"
        )
        
        assert template.id == "user123_simple_name"
    
    def test_id_generation_special_chars(self, template_manager):
        """Test ID generation with special characters"""
        template = template_manager.create_template(
            "Name with $pecial Ch@rs!",
            "Query",
            "user123"
        )
        
        # Should convert to valid slug
        assert "pecial" in template.id or "name_with" in template.id
        assert "$" not in template.id
        assert "@" not in template.id
    
    def test_id_generation_whitespace(self, template_manager):
        """Test ID generation with multiple spaces"""
        template = template_manager.create_template(
            "  Multiple   Spaces  ",
            "Query",
            "user123"
        )
        
        # Should collapse spaces and trim
        assert template.id.startswith("user123_")
        assert "  " not in template.id


class TestQueryTemplatePersistence:
    """Tests for template persistence across instances"""
    
    def test_persistence_across_instances(self, temp_storage_dir):
        """Test that templates persist across manager instances"""
        # Create template with first manager
        manager1 = QueryTemplateManager(storage_dir=temp_storage_dir)
        template = manager1.create_template(
            "Persistent Template",
            "Test query",
            "user123"
        )
        
        # Create new manager and verify template exists
        manager2 = QueryTemplateManager(storage_dir=temp_storage_dir)
        retrieved = manager2.get_template(template.id)
        
        assert retrieved is not None
        assert retrieved.name == "Persistent Template"
        assert retrieved.query == "Test query"
    
    def test_usage_count_persists(self, temp_storage_dir):
        """Test that usage count persists across instances"""
        manager1 = QueryTemplateManager(storage_dir=temp_storage_dir)
        template = manager1.create_template("Test", "Query", "user123")
        
        # Use template multiple times
        manager1.use_template(template.id)
        manager1.use_template(template.id)
        manager1.use_template(template.id)
        
        # Verify in new instance
        manager2 = QueryTemplateManager(storage_dir=temp_storage_dir)
        retrieved = manager2.get_template(template.id)
        
        assert retrieved.use_count == 3

