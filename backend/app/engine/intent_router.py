"""
Intent Router

Classifies user intent and routes to appropriate processing tier.
"""
import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from ..llm import get_llm_provider, get_model_for_task, ModelTier

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    """User intent types."""
    QUESTION = "question"           # Asking about the project
    DECISION = "decision"           # Making or discussing a decision
    COMMITMENT = "commitment"       # Making a commitment
    CONSTRAINT = "constraint"       # Setting a constraint
    GOAL = "goal"                   # Setting or discussing goals
    FAILURE = "failure"             # Reporting something that didn't work
    TASK = "task"                   # Task management
    CLARIFICATION = "clarification" # Clarifying something
    GREETING = "greeting"           # Small talk
    MEMORY_QUERY = "memory_query"   # Asking about memory
    CONFLICT = "conflict"           # Addressing a conflict
    EXCEPTION = "exception"         # Requesting an exception


class IntentClassification(BaseModel):
    """Result of intent classification."""
    intent: str = "question"
    confidence: float = 0.8
    requires_memory: bool = True
    requires_enforcement: bool = False
    suggested_tier: str = "mid"


class IntentRouter:
    """
    Intent router for classifying messages and selecting processing tier.
    
    Uses cheap model for quick classification.
    Determines:
    - Intent type
    - Whether memory is needed
    - Whether enforcement check is needed
    - Model tier to use
    """
    
    # Intent to tier mapping
    TIER_MAP = {
        Intent.GREETING: ModelTier.CHEAP,
        Intent.QUESTION: ModelTier.MID,
        Intent.CLARIFICATION: ModelTier.MID,
        Intent.DECISION: ModelTier.MID,
        Intent.COMMITMENT: ModelTier.HEAVY,
        Intent.CONSTRAINT: ModelTier.HEAVY,
        Intent.GOAL: ModelTier.MID,
        Intent.FAILURE: ModelTier.MID,
        Intent.TASK: ModelTier.CHEAP,
        Intent.MEMORY_QUERY: ModelTier.MID,
        Intent.CONFLICT: ModelTier.HEAVY,
        Intent.EXCEPTION: ModelTier.HEAVY,
    }
    
    # Intents that require enforcement
    ENFORCEMENT_INTENTS = {
        Intent.DECISION,
        Intent.COMMITMENT,
        Intent.CONSTRAINT,
        Intent.GOAL,
        Intent.FAILURE,
    }
    
    # Intents that don't need memory
    NO_MEMORY_INTENTS = {
        Intent.GREETING,
    }
    
    def __init__(self):
        self.llm = get_llm_provider()
    
    async def classify(self, message: str) -> IntentClassification:
        """
        Classify user intent from message.
        
        Args:
            message: User's message
            
        Returns:
            IntentClassification with intent and routing info
        """
        # Quick heuristic checks first
        lower = message.lower().strip()
        
        # Greeting detection
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon"]
        if any(lower.startswith(g) for g in greetings) and len(message) < 50:
            return IntentClassification(
                intent=Intent.GREETING.value,
                confidence=0.9,
                requires_memory=False,
                requires_enforcement=False,
                suggested_tier=ModelTier.CHEAP.value,
            )
        
        # Commitment detection
        commitment_phrases = [
            "we will", "i commit", "we commit", "i promise",
            "we promise", "always", "never", "must", "from now on"
        ]
        if any(p in lower for p in commitment_phrases):
            return IntentClassification(
                intent=Intent.COMMITMENT.value,
                confidence=0.8,
                requires_memory=True,
                requires_enforcement=True,
                suggested_tier=ModelTier.HEAVY.value,
            )
        
        # Constraint detection
        constraint_phrases = [
            "cannot", "must not", "should not", "only", "never use",
            "always use", "required", "forbidden", "not allowed"
        ]
        if any(p in lower for p in constraint_phrases):
            return IntentClassification(
                intent=Intent.CONSTRAINT.value,
                confidence=0.8,
                requires_memory=True,
                requires_enforcement=True,
                suggested_tier=ModelTier.HEAVY.value,
            )
        
        # Decision detection
        decision_phrases = [
            "decided", "we chose", "i chose", "let's go with",
            "we're going with", "decision:", "choosing", "picked"
        ]
        if any(p in lower for p in decision_phrases):
            return IntentClassification(
                intent=Intent.DECISION.value,
                confidence=0.8,
                requires_memory=True,
                requires_enforcement=True,
                suggested_tier=ModelTier.MID.value,
            )
        
        # Goal detection
        goal_phrases = [
            "goal is", "objective is", "aim to", "target is",
            "we want to", "trying to achieve", "our goal", "the goal",
            "mission is", "purpose is", "intend to", "plan to achieve",
            "by end of", "by q1", "by q2", "by q3", "by q4"
        ]
        if any(p in lower for p in goal_phrases):
            return IntentClassification(
                intent=Intent.GOAL.value,
                confidence=0.8,
                requires_memory=True,
                requires_enforcement=True,
                suggested_tier=ModelTier.MID.value,
            )
        
        # Failure detection
        failure_phrases = [
            "didn't work", "failed", "doesn't work", "broken",
            "tried and", "attempted but", "couldn't get", "unable to",
            "gave up on", "abandoned", "scrapped", "reverted",
            "rolled back", "backed out", "won't work", "not working"
        ]
        if any(p in lower for p in failure_phrases):
            return IntentClassification(
                intent=Intent.FAILURE.value,
                confidence=0.8,
                requires_memory=True,
                requires_enforcement=True,
                suggested_tier=ModelTier.MID.value,
            )
        
        # Memory query detection
        memory_phrases = [
            "what did we decide", "what was the decision",
            "remind me", "what's our", "what is our",
            "why did we", "when did we"
        ]
        if any(p in lower for p in memory_phrases):
            return IntentClassification(
                intent=Intent.MEMORY_QUERY.value,
                confidence=0.9,
                requires_memory=True,
                requires_enforcement=False,
                suggested_tier=ModelTier.MID.value,
            )

        # Question detection
        if "?" in message or lower.startswith(("what", "why", "how", "when", "where", "who", "can")):
            return IntentClassification(
                intent=Intent.QUESTION.value,
                confidence=0.8,
                requires_memory=True,
                requires_enforcement=False,
                suggested_tier=ModelTier.MID.value,
            )
        
        # Default to question
        return IntentClassification(
            intent=Intent.QUESTION.value,
            confidence=0.6,
            requires_memory=True,
            requires_enforcement=False,
            suggested_tier=ModelTier.MID.value,
        )
    
    def get_tier_for_intent(self, intent: Intent) -> ModelTier:
        """Get the recommended model tier for an intent."""
        return self.TIER_MAP.get(intent, ModelTier.MID)
    
    def should_enforce(self, intent: Intent) -> bool:
        """Check if intent requires enforcement checking."""
        return intent in self.ENFORCEMENT_INTENTS
    
    def needs_memory(self, intent: Intent) -> bool:
        """Check if intent needs memory context."""
        return intent not in self.NO_MEMORY_INTENTS
