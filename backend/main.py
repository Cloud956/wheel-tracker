from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from auth import verify_token, format_currency
from routers import account

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(account.router)

@app.get("/sync")
def sync_data(user: dict = Depends(verify_token)):
    print(f"User email: {user.get('email')}")
    # Fake sync always succeeds
    return {"status": "success", "new_trades_added": 0}

@app.get("/wheel-summary")
def get_wheel_summary(user: dict = Depends(verify_token)):
    # Fake wheel summary data
    return [
        {
            "wheelNum": 3,
            "symbol": "FAKE",
            "strike": "$150.0",
            "startDate": "2023-11-01",
            "endDate": "2023-12-01",
            "netCash": 120.50,
            "isOpen": False,
            "pnl": format_currency(120.50),
            "comm": format_currency(2.50)
        },
        {
            "wheelNum": 2,
            "symbol": "TEST",
            "strike": "$100.0",
            "startDate": "2023-10-15",
            "endDate": "2023-11-15",
            "netCash": -50.00,
            "isOpen": True,
            "pnl": format_currency(-50.00),
            "comm": format_currency(1.25)
        },
        {
            "wheelNum": 1,
            "symbol": "DEMO",
            "strike": "$25.0",
            "startDate": "2023-09-01",
            "endDate": "2023-10-01",
            "netCash": 450.00,
            "isOpen": False,
            "pnl": format_currency(450.00),
            "comm": format_currency(5.00)
        }
    ]

@app.get("/history")
def get_history(user: dict = Depends(verify_token)):
    # Fake history data
    return [
        {
            "date": "2023-12-01",
            "symbol": "FAKE",
            "details": "150.0 P OPT",
            "qty": -1,
            "price": "$1.20",
            "comm": format_currency(1.25)
        },
        {
            "date": "2023-11-15",
            "symbol": "TEST",
            "details": "100.0 C OPT",
            "qty": 1,
            "price": "$0.50",
            "comm": format_currency(1.25)
        },
        {
            "date": "2023-10-01",
            "symbol": "DEMO",
            "details": "25.0 P OPT",
            "qty": -10,
            "price": "$0.45",
            "comm": format_currency(5.00)
        }
    ]
