"""Initial schema with PostGIS

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import geoalchemy2

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("phone", sa.String(20), unique=True, nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_verified", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("location", geoalchemy2.Geography("POINT", srid=4326), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("is_available", sa.Boolean, default=True),
        sa.Column("vehicle_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_location ON users USING gist (location)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")

    op.create_table(
        "donations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("donor_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("food_type", sa.String(20), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("quantity_serves", sa.Integer, nullable=False),
        sa.Column("expiry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pickup_location", geoalchemy2.Geography("POINT", srid=4326), nullable=False),
        sa.Column("pickup_address", sa.Text, nullable=False),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), default="available"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_donations_location ON donations USING gist (pickup_location)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_donations_expiry ON donations (expiry_time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_donations_status ON donations (status)")

    op.create_table(
        "requests",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("requester_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("people_count", sa.Integer, nullable=False),
        sa.Column("urgency", sa.String(20), default="medium"),
        sa.Column("location", geoalchemy2.Geography("POINT", srid=4326), nullable=False),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_requests_location ON requests USING gist (location)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON requests (status)")

    op.create_table(
        "deliveries",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("donation_id", UUID(as_uuid=False), sa.ForeignKey("donations.id"), nullable=False),
        sa.Column("request_id", UUID(as_uuid=False), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("volunteer_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), default="posted"),
        sa.Column("distance_km", sa.Float, nullable=True),
        sa.Column("estimated_minutes", sa.Float, nullable=True),
        sa.Column("otp", sa.String(6), nullable=True),
        sa.Column("otp_verified", sa.Boolean, default=False),
        sa.Column("volunteer_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_volunteer ON deliveries (volunteer_id)")

    op.create_table(
        "otp_verifications",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("delivery_id", UUID(as_uuid=False), sa.ForeignKey("deliveries.id"), nullable=False),
        sa.Column("otp_code", sa.String(6), nullable=False),
        sa.Column("is_used", sa.Boolean, default=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "activity_logs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("activity_type", sa.String(50), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("donation_id", UUID(as_uuid=False), sa.ForeignKey("donations.id"), nullable=True),
        sa.Column("delivery_id", UUID(as_uuid=False), sa.ForeignKey("deliveries.id"), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("location_name", sa.String(200), nullable=True),
        sa.Column("extra_data", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_logs (activity_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_logs (created_at)")


def downgrade():
    op.drop_table("activity_logs")
    op.drop_table("otp_verifications")
    op.drop_table("deliveries")
    op.drop_table("requests")
    op.drop_table("donations")
    op.drop_table("users")
