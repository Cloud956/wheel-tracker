<<<<<<< HEAD
# wheel-tracker

I propose 2 folders

frontend - node
backend - python fastApi

Both need to be containerized simple Docker
=======
# Wheel Tracker - Backend

## Setup
1. Go to the `backend` folder.
2. Create a `.env` file with:
   - `IBKR_TOKEN=your_token`
   - `IBKR_QUERY_ID=your_id`
3. Install dependencies: `pip install -r requirements.txt`

## Running
Run `uvicorn main:app --reload` from the backend folder.
Access the data at `http://localhost:8000/wheel`.
>>>>>>> 16fb28a (Initial commit: Wheel tracker with commission-adjusted logic and multi-instance grouping)
