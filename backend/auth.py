from fastapi import HTTPException, Header
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "992920333249-jl7q5rghgbb09g3r2mjdqgorho0bnjkb.apps.googleusercontent.com")

def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        token = authorization.split(" ")[1] if " " in authorization else authorization
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        return id_info
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication Error: {str(e)}")

def format_currency(value):
    return {"value": f"${abs(value):,.2f}", "class": "text-green" if value >= 0 else "text-red", "raw": value}
