"""Strict yes/no reading of a patient's reply at an irreversible step (book, submit).

The reply must be made up *only* of words we recognise: yes-words, no-words and a
few neutral filler words. Anything else ("not sure", "ok so what's the address",
"no thanks, yes", "yes but Friday") is ambiguous and the caller should re-ask.
Matching is on whole words / phrases, never substrings.
"""

from __future__ import annotations

import re
from typing import Optional

YES_PHRASES = [
    "go ahead", "book it", "book that", "sounds good", "looks good", "of course",
    "that is right", "that is correct", "thats right", "thats correct", "do it",
    "send it", "submit it",
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
    "correct", "absolutely", "definitely", "certainly", "affirmative", "submit",
]

NO_PHRASES = [
    "go back", "never mind", "nevermind",
    "no", "nope", "nah", "cancel", "change", "different", "another", "back",
]

# Neutral words that may surround a yes/no without changing it. They also cover the
# quick-reply texts ("No, I'd like a different slot", "No, I need to change the details").
FILLERS = {
    "please", "it", "that", "this", "now", "the", "a", "an", "i", "id", "we",
    "would", "like", "to", "need", "want", "slot", "time", "details", "one", "my",
    "me", "for", "is", "its", "pick", "choose", "see", "other",
}

# Polite closers are fine after a yes ("yes thanks") but not after a no: "no thanks"
# could mean "not that slot" or "nothing more", so it is treated as ambiguous.
YES_ONLY_FILLERS = {"thanks", "thank", "you"}


def _tokens(text: str) -> list[str]:
    # Apostrophes are dropped so "that's" and "thats" (and "I'd" / "id") read the same.
    text = (text or "").lower().replace("’", "'").replace("'", "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return text.split()


def _consume(tokens: list[str]) -> tuple[bool, bool, bool, bool]:
    """Greedy left-to-right phrase match. Returns (saw_yes, saw_no, saw_yes_only_filler, leftover)."""
    phrases = sorted(
        [(p.split(), "yes") for p in YES_PHRASES] + [(p.split(), "no") for p in NO_PHRASES],
        key=lambda item: -len(item[0]),
    )
    saw_yes = saw_no = saw_polite = leftover = False
    i = 0
    while i < len(tokens):
        for words, kind in phrases:
            if tokens[i:i + len(words)] == words:
                saw_yes |= kind == "yes"
                saw_no |= kind == "no"
                i += len(words)
                break
        else:
            if tokens[i] in YES_ONLY_FILLERS:
                saw_polite = True
            elif tokens[i] not in FILLERS:
                leftover = True
            i += 1
    return saw_yes, saw_no, saw_polite, leftover


def classify_reply(text: str) -> Optional[str]:
    """Return "yes", "no", or None when the reply is ambiguous (caller should re-ask)."""
    tokens = _tokens(text)
    if not tokens:
        return None

    saw_yes, saw_no, saw_polite, leftover = _consume(tokens)
    if leftover or (saw_yes and saw_no):
        return None
    if saw_yes:
        return "yes"
    if saw_no and not saw_polite:
        return "no"
    return None
