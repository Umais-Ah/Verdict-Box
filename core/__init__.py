"""
VerdictBox Core Application Module
Core application setup, models, and extensions
"""

from .app import create_app
from .models import db
from .extensions import *

__all__ = ['create_app', 'db']
