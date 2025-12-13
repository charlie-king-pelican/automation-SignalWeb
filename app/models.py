"""
Database models for Copy Trade portal system.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Portal(db.Model):
    """
    Portal configuration model.
    Each portal represents an authenticated strategy page with custom branding.
    """
    __tablename__ = 'portals'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    profile_id = db.Column(db.String(100), nullable=False)
    strategy_id = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    theme_json = db.Column(db.Text, nullable=True, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Portal {self.name} ({self.slug})>'

    def to_dict(self):
        """Convert portal to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'profile_id': self.profile_id,
            'strategy_id': self.strategy_id,
            'is_active': self.is_active,
            'theme_json': self.theme_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
