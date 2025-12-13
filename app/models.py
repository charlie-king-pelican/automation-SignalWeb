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
    theme_json = db.Column(db.Text, nullable=False, default='{}')
    total_views = db.Column(db.Integer, default=0, nullable=False)
    successful_copies = db.Column(db.Integer, default=0, nullable=False)
    last_viewed_at = db.Column(db.DateTime, nullable=True)
    last_copied_at = db.Column(db.DateTime, nullable=True)
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


class PortalEvent(db.Model):
    """
    Portal analytics event tracking.
    Records view and copy events with UTC timestamps and daily deduplication.
    """
    __tablename__ = 'portal_events'

    id = db.Column(db.Integer, primary_key=True)
    portal_id = db.Column(db.Integer, db.ForeignKey('portals.id'), nullable=False, index=True)
    event_type = db.Column(db.String(20), nullable=False)  # 'view' or 'copy_success'
    profile_id = db.Column(db.String(100), nullable=True)
    copier_id = db.Column(db.String(100), nullable=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    event_day = db.Column(db.Date, nullable=False)

    # Unique constraint to dedupe views: one 'view' per profile per portal per day
    __table_args__ = (
        db.UniqueConstraint('portal_id', 'profile_id', 'event_day', 'event_type',
                            name='uq_portal_profile_day_event'),
        db.Index('idx_portal_occurred', 'portal_id', 'occurred_at'),
        db.Index('idx_portal_event_occurred', 'portal_id', 'event_type', 'occurred_at'),
    )

    def __repr__(self):
        return f'<PortalEvent {self.event_type} portal={self.portal_id} profile={self.profile_id}>'
