"""
Signals of the channels. The inbox listens to them to tell the team in real time, without the
channels knowing anything about the inbox.
"""

from django.dispatch import Signal

# The bot started (or stopped) answering a client of an account because of their faults.
# Arguments: account, contact_id and blocked_until (a date, or None when the block was lifted).
client_block_changed = Signal()
