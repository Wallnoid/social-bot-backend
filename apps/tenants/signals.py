"""
Signals of the businesses. Other apps listen to them without the businesses knowing about them.
"""

from django.dispatch import Signal

# The Social Bot team suspended a business. Argument: tenant.
business_suspended = Signal()
