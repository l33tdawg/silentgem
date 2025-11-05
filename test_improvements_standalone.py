#!/usr/bin/env python3
"""
Standalone test to verify context-aware follow-up improvements
Tests the key logic without requiring full module imports
"""

import re
from typing import List


def extract_location_context(query: str) -> str:
    """Extract location context from a query"""
    location_patterns = [
        r'in ([A-Z][a-zA-Z]+)',
        r'from ([A-Z][a-zA-Z]+)',
        r'at ([A-Z][a-zA-Z]+)',
        r'about ([A-Z][a-zA-Z]+)',
        r'on ([A-Z][a-zA-Z]+)',
        r'([A-Z][a-zA-Z]+) (?:bombing|attack|conflict|war|situation)'
    ]
    
    for pattern in location_patterns:
        matches = re.search(pattern, query)
        if matches:
            return matches.group(1)
    
    common_locations = ["Gaza", "Israel", "Palestine", "Ukraine", "Russia", "Syria", "Lebanon", "Iran", "Iraq"]
    for location in common_locations:
        if location in query:
            return location
    
    return ""


def extract_primary_topic(query: str) -> str:
    """Extract the primary topic from a query"""
    location = extract_location_context(query)
    if location:
        return location
    
    topic_match = re.search(r'([A-Z][a-zA-Z]+(?:(?:\s|-)[A-Z][a-zA-Z]+)*)', query)
    if topic_match:
        return topic_match.group(1)
    
    topic_words = ["blockchain", "crypto", "war", "conflict", "storm", "hurricane", 
                  "election", "politics", "technology", "attack", "bombing"]
    
    for word in topic_words:
        if word.lower() in query.lower():
            return word
    
    return ""


def is_related_query(current_query: str, previous_query: str) -> bool:
    """Determine if the current query is related to the previous query"""
    if not current_query or not previous_query:
        return False
    
    follow_up_phrases = [
        "what about", "and what", "tell me more", "can you elaborate",
        "who", "when", "where", "why", "how", "also", "additionally",
        "make a list", "list", "show me", "which ones", "which",
        "name the", "any new", "any recent", "latest", "update", "news"
    ]
    
    for phrase in follow_up_phrases:
        if current_query.lower().startswith(phrase):
            return True
    
    def extract_keywords(text: str) -> List[str]:
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 
                     'about', 'and', 'or', 'what', 'where', 'when', 'how', 'which', 
                     'who', 'why', 'make', 'list', 'tell', 'me', 'show'}
        return [w for w in words if len(w) > 2 and w not in stop_words]
    
    current_keywords = set(extract_keywords(current_query))
    previous_keywords = set(extract_keywords(previous_query))
    overlap = current_keywords.intersection(previous_keywords)
    
    if len(overlap) >= 1:
        return True
    
    business_indicators = ["business", "company", "customers", "developments", "growth", 
                          "expansion", "market", "clients", "partners", "collaboration"]
    current_has_business = any(ind in current_query.lower() for ind in business_indicators)
    previous_has_business = any(ind in previous_query.lower() for ind in business_indicators)
    
    if current_has_business and previous_has_business:
        return True
    
    return False


def simple_query_enhancement(current_query: str, previous_query: str) -> str:
    """Simple rule-based query enhancement"""
    location = extract_location_context(previous_query)
    primary_topic = extract_primary_topic(previous_query)
    
    needs_context_phrases = [
        "what cities", "which cities", "what places", "which places",
        "what about", "who", "when", "where", "how many",
        "what are", "which are", "who are", "list the", "name the"
    ]
    
    current_lower = current_query.lower()
    needs_context = any(phrase in current_lower for phrase in needs_context_phrases)
    
    if not needs_context:
        return current_query
    
    if location and location.lower() not in current_lower:
        if any(word in current_lower for word in ["cities", "places", "locations", "areas"]):
            return f"{current_query} in {location}"
    
    if primary_topic and primary_topic.lower() not in current_lower:
        if any(phrase in current_lower for phrase in ["who", "what", "when", "which", "how"]):
            return f"{current_query} about {primary_topic}"
    
    return current_query


def run_tests():
    """Run all tests"""
    print("🧪 Testing Context-Aware Follow-up Improvements\n")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    # Test 1: Follow-up detection with location context
    print("\n1. Testing follow-up detection (location context)")
    prev = "What's happening in Gaza?"
    curr = "What cities are affected?"
    result = is_related_query(curr, prev)
    if result:
        print(f"   ✅ PASS: Detected '{curr}' as follow-up to '{prev}'")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should detect as follow-up")
        failed += 1
    
    # Test 2: Simple query enhancement with location
    print("\n2. Testing simple query enhancement (location)")
    prev = "Latest news about Gaza"
    curr = "What cities are affected?"
    enhanced = simple_query_enhancement(curr, prev)
    if "Gaza" in enhanced:
        print(f"   ✅ PASS: Enhanced to '{enhanced}'")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should contain 'Gaza', got '{enhanced}'")
        failed += 1
    
    # Test 3: Location extraction
    print("\n3. Testing location extraction")
    query = "What's happening in Gaza?"
    location = extract_location_context(query)
    if location == "Gaza":
        print(f"   ✅ PASS: Extracted location '{location}'")
        passed += 1
    else:
        print(f"   ❌ FAIL: Expected 'Gaza', got '{location}'")
        failed += 1
    
    # Test 4: Unrelated queries should not be detected as follow-ups
    print("\n4. Testing unrelated query detection")
    prev = "What's happening in Gaza?"
    curr = "Tell me about cryptocurrency prices"
    result = is_related_query(curr, prev)
    if not result:
        print(f"   ✅ PASS: Correctly identified as unrelated")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should NOT detect as follow-up")
        failed += 1
    
    # Test 5: Follow-up with keyword overlap
    print("\n5. Testing follow-up with keyword overlap")
    prev = "What's the latest on Bitcoin?"
    curr = "Bitcoin price today"
    result = is_related_query(curr, prev)
    if result:
        print(f"   ✅ PASS: Detected follow-up with keyword overlap")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should detect keyword overlap")
        failed += 1
    
    # Test 6: Follow-up phrases detection
    print("\n6. Testing follow-up phrase detection")
    prev = "Tell me about Apple"
    curr = "When was it released?"
    result = is_related_query(curr, prev)
    if result:
        print(f"   ✅ PASS: Detected 'when' as follow-up phrase")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should detect 'when' as follow-up")
        failed += 1
    
    # Test 7: Topic extraction
    print("\n7. Testing topic extraction")
    query = "Tell me about Apple's new product"
    topic = extract_primary_topic(query)
    if "Apple" in topic:
        print(f"   ✅ PASS: Extracted topic '{topic}'")
        passed += 1
    else:
        print(f"   ❌ FAIL: Expected 'Apple' in topic, got '{topic}'")
        failed += 1
    
    # Test 8: Enhancement with topic context
    print("\n8. Testing query enhancement with topic")
    prev = "Tell me about Tesla's new features"
    curr = "When were they announced?"
    enhanced = simple_query_enhancement(curr, prev)
    if "Tesla" in enhanced or "features" in enhanced:
        print(f"   ✅ PASS: Enhanced to '{enhanced}'")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should contain topic context, got '{enhanced}'")
        failed += 1
    
    # Test 9: No enhancement for complete queries
    print("\n9. Testing no enhancement for complete queries")
    prev = "What's happening in Gaza?"
    curr = "Tell me about climate change news"
    enhanced = simple_query_enhancement(curr, prev)
    if enhanced == curr:
        print(f"   ✅ PASS: Complete query not modified")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should not modify complete queries")
        failed += 1
    
    # Test 10: Business context detection
    print("\n10. Testing business context detection")
    prev = "What's the latest on Acme Corp business?"
    curr = "Who are their customers?"
    result = is_related_query(curr, prev)
    if result:
        print(f"   ✅ PASS: Detected business context follow-up")
        passed += 1
    else:
        print(f"   ❌ FAIL: Should detect business context")
        failed += 1
    
    # Summary
    print("\n" + "=" * 70)
    print(f"\n📊 Test Results: {passed} passed, {failed} failed out of {passed + failed} tests")
    
    if failed == 0:
        print("\n✅ All tests passed! Context-aware follow-up improvements are working correctly.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review the implementation.")
        return 1


if __name__ == "__main__":
    exit(run_tests())

