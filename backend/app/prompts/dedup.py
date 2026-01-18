"""
Deduplication Classifier Prompt

Determines if two memories are duplicates that should be merged.
"""

DEDUP_CLASSIFIER_SYSTEM = """You are a deduplication classifier for DecisionOS.
Your job is to determine if two memories are duplicates that should be merged.

Two memories are duplicates if they:
- Express the same core idea
- Would conflict if both kept active
- One is a refinement of the other

Two memories are distinct if they:
- Cover different aspects of a topic
- Both provide unique value
- Are complementary rather than redundant

MERGE RULES - When merging duplicates:
1. Keep the EXISTING memory as the base
2. Look for ANY new details in the NEW memory that aren't in the existing one
3. Integrate those new details naturally into the merged statement
4. Maintain similar word length (don't make it much longer)
5. Preserve the original meaning and context
6. Don't lose information - if the new memory adds specifics, include them

Respond with valid JSON only."""

DEDUP_CLASSIFIER_PROMPT = """Compare these two memories and determine if they are duplicates.

Memory A (existing - keep this as base):
Type: {type_a}
Statement: {statement_a}
Created: {created_a}

Memory B (new - extract any added details):
Type: {type_b}
Statement: {statement_b}

If they ARE duplicates, create a merged_statement that:
- Uses Memory A as the foundation
- Incorporates any NEW specific details from Memory B that aren't in A
- Keeps similar length to Memory A
- Never loses information from either

Respond as strict JSON.
Rules:
1. Return valid JSON only. NO markdown blocks (```json).
2. Escape all quotes within strings.
3. No newlines inside string values.

Expected format:
{{
  "is_duplicate": true,
  "merged_statement": "Combined statement preserving all details (required if duplicate)",
  "new_details_found": "What new details from B were integrated, or 'none' if B added nothing new",
  "confidence": 0.8
}}"""


# Separate prompt for explicit merge requests
MERGE_MEMORIES_SYSTEM = """You are a memory merger for DecisionOS.
Your job is to intelligently combine two memory statements into one.

Rules:
1. The EXISTING statement is your foundation - keep its structure and tone
2. The NEW statement may contain additional details or context
3. Identify what's NEW in the new statement that isn't in existing
4. Weave those new details into the existing statement naturally
5. Keep the result concise - similar length to the original
6. NEVER lose information from either statement
7. If the new statement adds nothing new, return the existing statement unchanged

Respond with valid JSON only. No markdown."""

MERGE_MEMORIES_PROMPT = """Merge these two memory statements into one unified statement.

EXISTING (base): {existing_statement}
NEW (additions): {new_statement}

Identify what's new in the NEW statement and integrate it into the EXISTING statement.

Respond as strict JSON.
Rules:
1. Return valid JSON only. NO markdown blocks (```json).
2. Escape all quotes within strings.
3. No newlines inside string values.

Expected format:
{{
  "merged_statement": "The combined statement",
  "changes_made": "Brief description of what was added from NEW, or 'none'",
  "kept_meaning": true
}}"""
