
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile
from app.schemas import ProfileCreate, ProfileResponse
from app.utils.logger import logger

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("/", response_model=ProfileResponse)
async def create_profile(profile: ProfileCreate, db: Session = Depends(get_db)):
    """
    Create a new profile in the database

    This is called after user approval from the frontend
    """
    try:
        # Create new profile
        db_profile = Profile(
            name=profile.name,
            github_url=profile.github_url,
            instagram_url=profile.instagram_url,
            twitter_url=profile.twitter_url,
            linkedin_url=profile.linkedin_url,
            spotify_url=profile.spotify_url,
            tiktok_url=profile.tiktok_url,
            snapchat_url=profile.snapchat_url,
            tumblr_url=profile.tumblr_url,
            youtube_url=profile.youtube_url,
            reddit_url=profile.reddit_url,
            facebook_url=profile.facebook_url,
            pinterest_url=profile.pinterest_url,
            medium_url=profile.medium_url,
            threads_url=profile.threads_url,
            steam_url=profile.steam_url,
            tinder_mention=profile.tinder_mention,
            bumble_mention=profile.bumble_mention,
            discord_mention=profile.discord_mention,
            phone_numbers=profile.phone_numbers,
            description=profile.description,
            additional_info=profile.additional_info,
            similar_profiles=profile.similar_profiles,
            cross_validation_issues=profile.cross_validation_issues,
            network_connections=profile.network_connections,
            email_addresses=profile.email_addresses,
            data_breaches=profile.data_breaches,
        )

        db.add(db_profile)
        db.commit()
        db.refresh(db_profile)

        logger.log_success(f"Profile saved to database matrix: {profile.name}")
        return db_profile

    except Exception as e:
        db.rollback()
        logger.log_error(f"Error saving profile parameters: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {str(e)}") from e


@router.get("/", response_model=list[ProfileResponse])
async def get_all_profiles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all profiles from database"""
    try:
        profiles = db.query(Profile).offset(skip).limit(limit).all()
        return profiles

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profiles: {str(e)}") from e


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: int, db: Session = Depends(get_db)):
    """Get a specific profile by ID"""
    try:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()

        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        return profile

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}") from e


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    """Delete a profile"""
    try:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()

        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        db.delete(profile)
        db.commit()

        logger.log_success(f"Profile deleted from archives: {profile.name}")
        return {"message": f"Profile {profile_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete profile: {str(e)}") from e


@router.get("/search/{name}", response_model=list[ProfileResponse])
async def search_profiles_by_name(name: str, db: Session = Depends(get_db)):
    """Search profiles by name"""
    try:
        profiles = db.query(Profile).filter(Profile.name.ilike(f"%{name}%")).all()
        return profiles

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search profiles: {str(e)}") from e
