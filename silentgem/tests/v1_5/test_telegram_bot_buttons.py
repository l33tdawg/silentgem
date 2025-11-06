"""
Unit tests for telegram_bot.py button rendering

Tests the inline keyboard creation and callback handling for v1.5 features.
"""

import pytest
from unittest.mock import Mock, MagicMock
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from silentgem.bot.guided_queries import (
    GuidedQuerySuggestions,
    GuidedQuery,
    ExpandableTopic,
    ActionButton
)


# Mock the InsightsBot class to test button creation
class MockInsightsBot:
    """Mock InsightsBot for testing"""
    
    def __init__(self):
        self.config = {}
        self.bot = None
        self.command_handler = None
    
    def _truncate_text(self, text, max_length):
        """
        Truncate text at word boundary for better readability
        """
        if len(text) <= max_length:
            return text
        
        # Find the last space before max_length
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.7:  # Only use space if it's not too far back
            truncated = truncated[:last_space]
        
        return truncated.rstrip('.,!?;:') + '...'
    
    def _create_inline_keyboard(self, suggestions):
        """
        Create an inline keyboard from guided query suggestions
        This is the actual method from telegram_bot.py
        """
        if not suggestions:
            return None
        
        keyboard = []
        
        # Add follow-up question buttons (max 3)
        # Use longer limit and smart truncation for better clarity
        for i, question in enumerate(suggestions.follow_up_questions[:3], 1):
            # Format: "1. Question text..."
            button_text = f"{i}. {self._truncate_text(question.question, 95)}"
            keyboard.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"suggest:{i-1}"
                )
            ])
        
        # Add expandable topic buttons (if any)
        for topic in suggestions.expandable_topics[:2]:
            topic_text = f"📖 {self._truncate_text(topic.label, 90)}"
            keyboard.append([
                InlineKeyboardButton(
                    text=topic_text,
                    callback_data=f"expand:{topic.id}"
                )
            ])
        
        # Add action buttons in a row (max 2 per row)
        action_row = []
        for button in suggestions.action_buttons[:4]:
            action_row.append(
                InlineKeyboardButton(
                    text=button.label,
                    callback_data=button.callback_data
                )
            )
            if len(action_row) == 2:
                keyboard.append(action_row)
                action_row = []
        
        if action_row:
            keyboard.append(action_row)
        
        return InlineKeyboardMarkup(keyboard) if keyboard else None


@pytest.fixture
def mock_bot():
    """Create a mock bot instance"""
    return MockInsightsBot()


@pytest.fixture
def simple_suggestions():
    """Create simple guided query suggestions"""
    return GuidedQuerySuggestions(
        follow_up_questions=[
            GuidedQuery("What are the deadlines?", "Timeline needed", "timeline"),
            GuidedQuery("Who is involved?", "Contributors matter", "people")
        ],
        expandable_topics=[],
        action_buttons=[],
        reasoning="Test suggestions"
    )


@pytest.fixture
def full_suggestions():
    """Create full guided query suggestions with all types"""
    return GuidedQuerySuggestions(
        follow_up_questions=[
            GuidedQuery("Question 1", "Reason 1", "deep_dive"),
            GuidedQuery("Question 2", "Reason 2", "timeline"),
            GuidedQuery("Question 3", "Reason 3", "people")
        ],
        expandable_topics=[
            ExpandableTopic("topic1", "Topic 1 Details", 10, "Substantial", 1),
            ExpandableTopic("topic2", "Topic 2 Details", 15, "Important", 2)
        ],
        action_buttons=[
            ActionButton("timeline", "📅 Timeline", "action:timeline", "useful"),
            ActionButton("contributors", "👥 Contributors", "action:contributors", "helpful"),
            ActionButton("save_template", "💾 Save", "action:save_template", "convenient")
        ],
        reasoning="Full test suggestions"
    )


class TestBasicButtonCreation:
    """Tests for basic inline keyboard creation"""
    
    def test_create_keyboard_with_no_suggestions(self, mock_bot):
        """Test that None suggestions returns None keyboard"""
        keyboard = mock_bot._create_inline_keyboard(None)
        assert keyboard is None
    
    def test_create_keyboard_with_simple_suggestions(self, mock_bot, simple_suggestions):
        """Test creating keyboard with just follow-up questions"""
        keyboard = mock_bot._create_inline_keyboard(simple_suggestions)
        
        assert keyboard is not None
        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) == 2  # 2 follow-up questions
    
    def test_follow_up_button_format(self, mock_bot, simple_suggestions):
        """Test that follow-up buttons are formatted correctly"""
        keyboard = mock_bot._create_inline_keyboard(simple_suggestions)
        
        first_button = keyboard.inline_keyboard[0][0]
        assert first_button.text.startswith("1. ")
        assert "What are the deadlines?" in first_button.text
        assert first_button.callback_data == "suggest:0"
    
    def test_callback_data_zero_indexed(self, mock_bot, simple_suggestions):
        """Test that callback data uses zero-based indexing"""
        keyboard = mock_bot._create_inline_keyboard(simple_suggestions)
        
        assert keyboard.inline_keyboard[0][0].callback_data == "suggest:0"
        assert keyboard.inline_keyboard[1][0].callback_data == "suggest:1"


class TestButtonLimits:
    """Tests for button count limits"""
    
    def test_max_three_follow_up_questions(self, mock_bot):
        """Test that at most 3 follow-up questions are shown"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[
                GuidedQuery(f"Question {i}", "Reason", "general")
                for i in range(10)  # Create 10 questions
            ],
            expandable_topics=[],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        # Count question buttons (they have "suggest:" callback)
        question_buttons = [
            row for row in keyboard.inline_keyboard
            if row[0].callback_data.startswith("suggest:")
        ]
        assert len(question_buttons) == 3
    
    def test_max_two_expandable_topics(self, mock_bot):
        """Test that at most 2 expandable topics are shown"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[
                ExpandableTopic(f"topic{i}", f"Topic {i}", 10, "Reason", 1)
                for i in range(5)  # Create 5 topics
            ],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        # Count topic buttons (they have "expand:" callback)
        topic_buttons = [
            row for row in keyboard.inline_keyboard
            if row[0].callback_data.startswith("expand:")
        ]
        assert len(topic_buttons) == 2
    
    def test_max_four_action_buttons(self, mock_bot):
        """Test that at most 4 action buttons are shown"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[],
            action_buttons=[
                ActionButton(f"action{i}", f"Action {i}", f"action:action{i}", "test")
                for i in range(10)  # Create 10 actions
            ]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        # Count total action buttons
        action_button_count = sum(
            len(row) for row in keyboard.inline_keyboard
        )
        assert action_button_count == 4


class TestTextTruncation:
    """Tests for text truncation in buttons"""
    
    def test_word_boundary_truncation(self, mock_bot):
        """Test that truncation happens at word boundaries, not mid-word"""
        # Create a question where truncation would normally cut a word
        question = "Can you provide more context about the proposal being drafted for Satra which involves reviewing"
        
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[
                GuidedQuery(question, "Reason", "general")
            ],
            expandable_topics=[],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        button_text = keyboard.inline_keyboard[0][0].text
        
        # Should end with "..." and not cut a word in half
        if button_text.endswith("..."):
            # Get the text before the ellipsis
            text_before_ellipsis = button_text[:-3].rstrip()
            # The last character should be a space or end of a word, not mid-word
            # Check that we're not cutting "reviewing" as "reviewi..."
            assert not text_before_ellipsis.endswith("reviewi")
            assert not "reviewi..." in button_text
    
    def test_long_question_truncated(self, mock_bot):
        """Test that long questions are truncated with ellipsis"""
        long_question = "This is a very long question that exceeds the ninety-five character limit and should be truncated at a word boundary for better readability"
        
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[
                GuidedQuery(long_question, "Reason", "general")
            ],
            expandable_topics=[],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        button_text = keyboard.inline_keyboard[0][0].text
        
        assert button_text.endswith("...")
        # Should be truncated around 95 chars + "1. " prefix
        assert len(button_text) <= 102  # 95 + "1. " + "..."
        # Check that truncation happens at word boundary (no mid-word cuts)
        # The text before ... should end with a complete word
        text_without_ellipsis = button_text[3:-3]  # Remove "1. " and "..."
        assert not text_without_ellipsis[-1].isalnum() or ' ' in text_without_ellipsis
    
    def test_short_question_not_truncated(self, mock_bot):
        """Test that short questions are not truncated"""
        short_question = "Short question"
        
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[
                GuidedQuery(short_question, "Reason", "general")
            ],
            expandable_topics=[],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        button_text = keyboard.inline_keyboard[0][0].text
        
        assert not button_text.endswith("...")
        assert short_question in button_text
    
    def test_long_topic_label_truncated(self, mock_bot):
        """Test that long topic labels are truncated"""
        long_label = "This is a very long topic label that exceeds ninety characters and needs to be truncated at word boundaries for clarity"
        
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[
                ExpandableTopic("topic1", long_label, 10, "Reason", 1)
            ],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        button_text = keyboard.inline_keyboard[0][0].text
        
        assert button_text.endswith("...")
        # Should be truncated around 90 chars + emoji prefix
        assert len(button_text) <= 97  # 90 + "📖 " + "..."


class TestCallbackData:
    """Tests for callback data format"""
    
    def test_suggest_callback_format(self, mock_bot, simple_suggestions):
        """Test suggest callback data format"""
        keyboard = mock_bot._create_inline_keyboard(simple_suggestions)
        
        callback = keyboard.inline_keyboard[0][0].callback_data
        assert callback.startswith("suggest:")
        assert callback.split(":")[1].isdigit()
    
    def test_expand_callback_format(self, mock_bot):
        """Test expand callback data format"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[
                ExpandableTopic("my_topic_id", "Topic", 10, "Reason", 1)
            ],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        callback = keyboard.inline_keyboard[0][0].callback_data
        
        assert callback == "expand:my_topic_id"
    
    def test_action_callback_format(self, mock_bot):
        """Test action callback data format"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[],
            action_buttons=[
                ActionButton("timeline", "Timeline", "action:timeline", "test")
            ]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        callback = keyboard.inline_keyboard[0][0].callback_data
        
        assert callback == "action:timeline"


class TestButtonLayout:
    """Tests for button layout and organization"""
    
    def test_follow_up_buttons_one_per_row(self, mock_bot, simple_suggestions):
        """Test that follow-up questions are one per row"""
        keyboard = mock_bot._create_inline_keyboard(simple_suggestions)
        
        # First two rows should be follow-up questions
        assert len(keyboard.inline_keyboard[0]) == 1  # One button per row
        assert len(keyboard.inline_keyboard[1]) == 1
    
    def test_expandable_topics_one_per_row(self, mock_bot):
        """Test that expandable topics are one per row"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[
                ExpandableTopic("topic1", "Topic 1", 10, "R", 1),
                ExpandableTopic("topic2", "Topic 2", 10, "R", 1)
            ],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        assert len(keyboard.inline_keyboard[0]) == 1
        assert len(keyboard.inline_keyboard[1]) == 1
    
    def test_action_buttons_two_per_row(self, mock_bot):
        """Test that action buttons are arranged 2 per row"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[],
            action_buttons=[
                ActionButton("action1", "Action 1", "action:action1", "test"),
                ActionButton("action2", "Action 2", "action:action2", "test"),
                ActionButton("action3", "Action 3", "action:action3", "test"),
                ActionButton("action4", "Action 4", "action:action4", "test")
            ]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        # Should have 2 rows of 2 buttons each
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 2
    
    def test_odd_action_buttons_layout(self, mock_bot):
        """Test layout with odd number of action buttons"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[],
            action_buttons=[
                ActionButton("action1", "Action 1", "action:action1", "test"),
                ActionButton("action2", "Action 2", "action:action2", "test"),
                ActionButton("action3", "Action 3", "action:action3", "test")
            ]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        # Should have first row with 2, second row with 1
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 1


class TestFullKeyboard:
    """Tests for complete keyboards with all button types"""
    
    def test_full_keyboard_structure(self, mock_bot, full_suggestions):
        """Test keyboard with all button types"""
        keyboard = mock_bot._create_inline_keyboard(full_suggestions)
        
        assert keyboard is not None
        
        # Count different button types
        total_rows = len(keyboard.inline_keyboard)
        assert total_rows > 0
        
        # Should have questions, topics, and actions
        callbacks = [
            row[0].callback_data for row in keyboard.inline_keyboard
        ]
        
        has_suggest = any(cb.startswith("suggest:") for cb in callbacks)
        has_expand = any(cb.startswith("expand:") for cb in callbacks)
        has_action = any(cb.startswith("action:") for cb in callbacks)
        
        assert has_suggest
        assert has_expand
        assert has_action
    
    def test_button_order(self, mock_bot, full_suggestions):
        """Test that buttons appear in correct order"""
        keyboard = mock_bot._create_inline_keyboard(full_suggestions)
        
        callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
        
        # Find indices of different types
        suggest_indices = [i for i, cb in enumerate(callbacks) if cb.startswith("suggest:")]
        expand_indices = [i for i, cb in enumerate(callbacks) if cb.startswith("expand:")]
        action_indices = [i for i, cb in enumerate(callbacks) if cb.startswith("action:")]
        
        # Suggests should come first
        if suggest_indices and expand_indices:
            assert max(suggest_indices) < min(expand_indices)
        
        # Expands should come before actions
        if expand_indices and action_indices:
            assert max(expand_indices) < min(action_indices)


class TestEmptySuggestions:
    """Tests for edge cases with empty suggestion components"""
    
    def test_keyboard_with_only_questions(self, mock_bot):
        """Test keyboard with only follow-up questions"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[
                GuidedQuery("Question 1", "R", "general")
            ],
            expandable_topics=[],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
    
    def test_keyboard_with_only_topics(self, mock_bot):
        """Test keyboard with only expandable topics"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[
                ExpandableTopic("topic1", "Topic 1", 10, "R", 1)
            ],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
    
    def test_keyboard_with_only_actions(self, mock_bot):
        """Test keyboard with only action buttons"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[],
            action_buttons=[
                ActionButton("action1", "Action 1", "action:action1", "test")
            ]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
    
    def test_completely_empty_suggestions(self, mock_bot):
        """Test with suggestions object that has no buttons"""
        suggestions = GuidedQuerySuggestions(
            follow_up_questions=[],
            expandable_topics=[],
            action_buttons=[]
        )
        
        keyboard = mock_bot._create_inline_keyboard(suggestions)
        
        # Should return None when there are no buttons
        assert keyboard is None

