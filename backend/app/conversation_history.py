"""One ordered history for typed exchanges and finalized voice transcripts."""
from sqlalchemy import select
from app.models import VoiceMessage


async def merge_voice_history(db, conversation_id, typed):
    rows = await db.scalars(select(VoiceMessage).where(
        VoiceMessage.conversation_id == conversation_id,
    ).order_by(VoiceMessage.created_at, VoiceMessage.id))
    messages = list(typed)
    for row in rows:
        messages.append({
            'id': str(row.id), 'role': row.role, 'text': row.text,
            'status': 'completed', 'created_at': row.created_at,
            'interrupted': row.interrupted, 'source': 'voice',
            # Transcript is the framework's playout-adjusted text, not proof of hearing.
            'delivery': 'interrupted' if row.interrupted else 'playout_transcript',
        })
    return sorted(messages, key=lambda m: (m['created_at'], m['id']))
