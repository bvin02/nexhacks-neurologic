"""
Deduplication Classifier Prompt

Determines if two memories are duplicates that should be merged.
"""

DEDUP_CLASSIFIER_SYSTEM = """You are a deduplication classifier for DecisionOS.
Your job is to determine the relationship between two memories.

CONTRADICTION DETECTION - CHECK THIS FIRST!
A CONTRADICTION exists when:
- "use X" vs "don't use X" or "stop using X" or "not using X"
- "will do X" vs "won't do X" or "decided against X"
- "enable X" vs "disable X"
- "include X" vs "exclude X"  
- "start X" vs "stop X"
- Any negation words: "not", "don't", "won't", "stop", "no longer", "never"
- User explicitly changed their mind or reversed a prior decision

If ANY of these patterns match, return is_contradiction=true IMMEDIATELY.

DUPLICATE (is_duplicate=true, is_contradiction=false):
ONLY if both memories agree and point in the same direction:
- "use X" + "use X for purpose Y" = duplicate (adds detail)
- "build feature A" + "build feature A with tech B" = duplicate (adds detail)

DISTINCT (both false):
- Completely different topics with no relation

IMPORTANT: When in doubt between duplicate and contradiction, choose CONTRADICTION.
It's better to flag a potential conflict than to silently merge opposing decisions.

Respond with valid JSON only."""

DEDUP_CLASSIFIER_PROMPT = """Compare these two memories and classify their relationship.

Memory A (existing):
Type: {type_a}
Statement: {statement_a}
Created: {created_a}

Memory B (new):
Type: {type_b}
Statement: {statement_b}

FIRST CHECK FOR CONTRADICTION:
- Does B negate, reverse, or oppose A?
- Does B say "don't/stop/not/won't" when A says "do/use/will"?
- Did user change their mind?

If YES to any → is_contradiction=true, is_duplicate=false

EXAMPLES:
- A: "Use clinicaltrials.gov" + B: "Don't use clinicaltrials.gov" → CONTRADICTION
- A: "Use React" + B: "Use React with TypeScript" → DUPLICATE  
- A: "Build auth module" + B: "Don't build auth module" → CONTRADICTION
- A: "Use PostgreSQL" + B: "Use PostgreSQL with pgvector" → DUPLICATE

Respond as strict JSON.
Rules:
1. Return valid JSON only. NO markdown blocks.
2. Escape all quotes within strings.
3. No newlines inside string values.

Expected format:
{{
  "is_duplicate": false,
  "is_contradiction": true,
  "merged_statement": null,
  "new_details_found": null,
  "confidence": 0.95
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
