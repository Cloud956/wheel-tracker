from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from auth import verify_token
from database import get_user_config, update_user_config

router = APIRouter()

class AccountSettings(BaseModel):
    ibkr_token: Optional[str] = None
    ibkr_query_id: Optional[str] = None

@router.get("/account_settings", response_model=AccountSettings)
def get_settings(user: dict = Depends(verify_token)):
    email = user.get('email')
    if not email:
        raise HTTPException(status_code=400, detail="User email not found in token")
        
    config = get_user_config(email)
    if not config:
        return AccountSettings()
    
    # Filter to only return known fields
    return AccountSettings(
        ibkr_token=config.get('ibkr_token'),
        ibkr_query_id=config.get('ibkr_query_id')
    )

@router.post("/account_settings")
def update_settings(settings: AccountSettings, user: dict = Depends(verify_token)):
    email = user.get('email')
    if not email:
        raise HTTPException(status_code=400, detail="User email not found in token")
    
    # Filter out None values to only update what was sent
    update_data = {k: v for k, v in settings.dict().items() if v is not None}
    
    if not update_data:
        return {"status": "success", "message": "No changes to update"}

    success = update_user_config(email, update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update settings in database")
        
    return {"status": "success", "updated_fields": list(update_data.keys())}
