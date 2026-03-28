import json
from sqlalchemy.orm import Session
from app.models.snapshot import ProfileSnapshot
from app.schemas.snapshot import FieldChange, ChangeReport
from app.utils.logger import logger


# Fields to track with their human-readable labels
TRACKED_FIELDS = {
    "github_url": "GitHub URL",
    "instagram_url": "Instagram URL",
    "twitter_url": "Twitter / X URL",
    "linkedin_url": "LinkedIn URL",
    "spotify_url": "Spotify URL",
    "tiktok_url": "TikTok URL",
    "description": "Bio / Profil Açıklaması",
}

# Dynamic fields stored inside snapshot_data JSON
TRACKED_SNAPSHOT_KEYS = {
    "location_country": "Tahmini Ülke",
    "location_city": "Tahmini Şehir",
    "social_media_score": "Sosyal Medya Skoru",
    "last_activity_summary": "Son Aktivite Özeti",
    "snapchat_url": "Snapchat URL",
    "tumblr_url": "Tumblr URL",
    "youtube_url": "YouTube URL",
    "reddit_url": "Reddit URL",
    "facebook_url": "Facebook URL",
    "pinterest_url": "Pinterest URL",
    "medium_url": "Medium URL",
    "threads_url": "Threads URL",
    "steam_url": "Steam URL",
    "tinder_mention": "Tinder Mention",
    "bumble_mention": "Bumble Mention",
    "discord_mention": "Discord Mention",
}


def _normalize_query(query: str) -> str:
    """Normalize a query string for consistent matching."""
    # Strip, lowercase, collapse whitespace
    return " ".join(query.lower().strip().split())


def _val_to_str(value) -> str | None:
    """Convert a value to a comparable string, or None if empty."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def save_snapshot(db: Session, query_name: str, search_response) -> ProfileSnapshot:
    """
    Save a snapshot of the current search results for version tracking.
    `search_response` can be a dict or a Pydantic model with the standard fields.
    """
    normalized = _normalize_query(query_name)

    def _get(field):
        if hasattr(search_response, field):
            return getattr(search_response, field)
        elif isinstance(search_response, dict):
            return search_response.get(field)
        return None

    # Build snapshot_data with dynamic fields
    snapshot_data = {key: _get(key) for key in TRACKED_SNAPSHOT_KEYS}

    additional_info = _get("additional_info")

    snapshot = ProfileSnapshot(
        query_name=normalized,
        github_url=_get("github_url"),
        instagram_url=_get("instagram_url"),
        twitter_url=_get("twitter_url"),
        linkedin_url=_get("linkedin_url"),
        spotify_url=_get("spotify_url"),
        tiktok_url=_get("tiktok_url"),
        description=_get("description"),
        additional_info=additional_info,
        snapshot_data=snapshot_data,
    )

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    logger.log_success(f"Version snapshot #{snapshot.id} saved for '{normalized}'")
    return snapshot


def get_snapshots(db: Session, query_name: str) -> list[ProfileSnapshot]:
    """Get all snapshots for a given query name, ordered oldest → newest."""
    normalized = _normalize_query(query_name)
    return (
        db.query(ProfileSnapshot)
        .filter(ProfileSnapshot.query_name == normalized)
        .order_by(ProfileSnapshot.captured_at.asc())
        .all()
    )


def get_snapshot_count(db: Session, query_name: str) -> int:
    """Get total snapshot count for a query name."""
    normalized = _normalize_query(query_name)
    return db.query(ProfileSnapshot).filter(ProfileSnapshot.query_name == normalized).count()


def generate_change_report(db: Session, query_name: str) -> ChangeReport | None:
    """
    Compare the two most recent snapshots and produce a change report.
    Returns None if there are fewer than 2 snapshots.
    """
    normalized = _normalize_query(query_name)

    # Get the last two snapshots (newest first)
    snapshots = (
        db.query(ProfileSnapshot)
        .filter(ProfileSnapshot.query_name == normalized)
        .order_by(ProfileSnapshot.captured_at.desc())
        .limit(2)
        .all()
    )

    total_count = get_snapshot_count(db, query_name)

    if len(snapshots) < 2:
        # Not enough data to compare — return empty report
        if len(snapshots) == 1:
            return ChangeReport(
                query_name=normalized,
                previous_captured_at=None,
                current_captured_at=snapshots[0].captured_at,
                changes=[],
                snapshot_count=total_count,
                has_changes=False,
            )
        return None

    current = snapshots[0]   # Newest
    previous = snapshots[1]  # Previous

    changes: list[FieldChange] = []

    # Compare standard tracked fields (columns on the model)
    for field, label in TRACKED_FIELDS.items():
        old_val = _val_to_str(getattr(previous, field, None))
        new_val = _val_to_str(getattr(current, field, None))

        if old_val != new_val:
            changes.append(FieldChange(
                field=field,
                field_label=label,
                old_value=old_val,
                new_value=new_val,
            ))

    # Compare dynamic snapshot_data fields
    prev_data = previous.snapshot_data or {}
    curr_data = current.snapshot_data or {}

    for key, label in TRACKED_SNAPSHOT_KEYS.items():
        old_val = _val_to_str(prev_data.get(key))
        new_val = _val_to_str(curr_data.get(key))

        if old_val != new_val:
            changes.append(FieldChange(
                field=key,
                field_label=label,
                old_value=old_val,
                new_value=new_val,
            ))

    # Compare additional_info (deep JSON diff — top-level keys only)
    prev_info = previous.additional_info or {}
    curr_info = current.additional_info or {}

    all_info_keys = set(list(prev_info.keys()) + list(curr_info.keys()))
    for key in sorted(all_info_keys):
        old_raw = prev_info.get(key)
        new_raw = curr_info.get(key)

        old_val = _val_to_str(json.dumps(old_raw, ensure_ascii=False)) if old_raw is not None else None
        new_val = _val_to_str(json.dumps(new_raw, ensure_ascii=False)) if new_raw is not None else None

        if old_val != new_val:
            changes.append(FieldChange(
                field=f"additional_info.{key}",
                field_label=f"Ek Bilgi: {key}",
                old_value=old_val,
                new_value=new_val,
            ))

    logger.log_action(f"Version diff for '{normalized}': {len(changes)} change(s) detected across {total_count} snapshots")

    return ChangeReport(
        query_name=normalized,
        previous_captured_at=previous.captured_at,
        current_captured_at=current.captured_at,
        changes=changes,
        snapshot_count=total_count,
        has_changes=len(changes) > 0,
    )
