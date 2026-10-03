"""Framework-neutral evidence validation shared by typed and live tools."""

def queue_memory(context, content, kind, evidence):
    content, evidence = content.strip(), evidence.strip()
    if context is None or not context.memory_allowed:
        return {'saved': False, 'reason': 'Memory is off.'}
    if kind not in {'context', 'preference', 'pattern', 'goal'}:
        return {'saved': False, 'reason': 'Only lasting facts, preferences, stated patterns, or long-term goals.'}
    if not content or len(content) > 500 or not evidence or len(evidence) > 220:
        return {'saved': False, 'reason': 'Use a brief fact with a short exact quote.'}
    if evidence.casefold() not in context.user_text.casefold():
        return {'saved': False, 'reason': 'Evidence must come from the latest message.'}
    if context.memory_changes:
        return {'saved': False, 'reason': 'At most one useful detail per turn; most turns need none.'}
    context.memory_changes.append({'content': content, 'kind': kind, 'evidence': evidence})
    return {'saved': True, 'note': 'Will be remembered after the reply succeeds. The user can edit or delete it.'}
