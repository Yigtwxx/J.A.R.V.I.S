from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Profile
from app.schemas import ProfileCreate, ProfileResponse

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
            description=profile.description,
            additional_info=profile.additional_info,
            similar_profiles=profile.similar_profiles
        )
        
        db.add(db_profile)
        db.commit()
        db.refresh(db_profile)
        
        from app.jarvis_logger import logger
        logger.log_success(f"Profile saved to database matrix: {profile.name}")
        return db_profile
    
    except Exception as e:
        db.rollback()
        from app.jarvis_logger import logger
        logger.log_error(f"Error saving profile parameters: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {str(e)}")


@router.get("/", response_model=List[ProfileResponse])
async def get_all_profiles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all profiles from database"""
    try:
        profiles = db.query(Profile).offset(skip).limit(limit).all()
        return profiles
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profiles: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    """Delete a profile"""
    try:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        db.delete(profile)
        db.commit()
        
        from app.jarvis_logger import logger
        logger.log_success(f"Profile deleted from archives: {profile.name}")
        return {"message": f"Profile {profile_id} deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete profile: {str(e)}")


@router.get("/search/{name}", response_model=List[ProfileResponse])
async def search_profiles_by_name(name: str, db: Session = Depends(get_db)):
    """Search profiles by name"""
    try:
        profiles = db.query(Profile).filter(Profile.name.ilike(f"%{name}%")).all()
        return profiles
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search profiles: {str(e)}")
