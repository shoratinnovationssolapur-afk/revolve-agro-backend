from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    Depends
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel, HttpUrl
from typing import Optional

import firebase_admin
from firebase_admin import (
    credentials,
    messaging,
    auth,
    firestore
)

from slowapi import Limiter
from slowapi.util import get_ipaddr
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

import os
import json
import logging
import uvicorn

# =========================================
# LOGGING
# =========================================

logging.basicConfig(level=logging.INFO)

# =========================================
# FASTAPI APP
# =========================================

app = FastAPI()

# =========================================
# RATE LIMITER
# =========================================

limiter = Limiter(key_func=get_ipaddr)

app.state.limiter = limiter

app.add_middleware(SlowAPIMiddleware)

# =========================================
# CORS
# =========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://revolve-agro-backend.onrender.com",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# FIREBASE INITIALIZATION
# =========================================

service_account_str = os.environ.get(
    "FIREBASE_SERVICE_ACCOUNT"
)

if not service_account_str:
    raise Exception(
        "FIREBASE_SERVICE_ACCOUNT environment variable missing"
    )

if not firebase_admin._apps:

    cred_json = json.loads(service_account_str)

    cred = credentials.Certificate(cred_json)

    firebase_admin.initialize_app(cred)

db = firestore.client()

# =========================================
# SECURITY HEADERS
# =========================================

@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next
):

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    return response

# =========================================
# RATE LIMIT EXCEPTION
# =========================================

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(
    request: Request,
    exc
):

    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "message": "Too many requests"
        }
    )

# =========================================
# REQUEST MODEL
# =========================================

class NotificationRequest(BaseModel):

    title: str
    body: str

    image: Optional[HttpUrl] = None

    topic: str = "agro_members"

    type: str = "simple"

    id: str = ""

# =========================================
# ALLOWED TOPICS
# =========================================

ALLOWED_TOPICS = [
    "agro_members",
    "farmers",
    "dealers",
    "weather_alerts"
]

# =========================================
# VERIFY ADMIN TOKEN
# =========================================

async def verify_admin_token(
    authorization: str = Header(None)
):

    if not authorization:

        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    if not authorization.startswith("Bearer "):

        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization format"
        )

    try:

        token = authorization.replace(
            "Bearer ",
            ""
        )

        decoded_token = auth.verify_id_token(token)

        uid = decoded_token["uid"]

        user_doc = db.collection("users").document(uid).get()

        if not user_doc.exists:

            raise HTTPException(
                status_code=403,
                detail="User not found"
            )

        role = user_doc.to_dict().get("role")

        if role not in ["admin", "super_admin"]:

            logging.warning(
                f"Unauthorized admin access attempt: {uid}"
            )

            raise HTTPException(
                status_code=403,
                detail="Admin access required"
            )

        return uid

    except HTTPException:
        raise

    except Exception as e:

        logging.error(
            f"Token verification failed: {str(e)}"
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

# =========================================
# ROOT ENDPOINT
# =========================================

@app.get("/")
async def root():

    return {
        "status": "active",
        "service": "agro-backend"
    }

# =========================================
# SEND NOTIFICATION
# =========================================

@app.post("/send-agro-notification")
@limiter.limit("5/minute")
async def send_agro_notification(
    request: Request,
    data: NotificationRequest,
    uid: str = Depends(verify_admin_token)
):

    # =====================================
    # VALIDATE TOPIC
    # =====================================

    if data.topic not in ALLOWED_TOPICS:

        raise HTTPException(
            status_code=400,
            detail="Invalid topic"
        )

    # =====================================
    # VALIDATE LENGTH
    # =====================================

    if len(data.title) > 100:

        raise HTTPException(
            status_code=400,
            detail="Title too long"
        )

    if len(data.body) > 500:

        raise HTTPException(
            status_code=400,
            detail="Body too long"
        )

    try:

        message_payload = messaging.Message(

            notification=messaging.Notification(
                title=data.title,
                body=data.body,
                image=str(data.image) if data.image else None
            ),

            data={
                "type": data.type,
                "productId": data.id,
                "click_action": "FLUTTER_NOTIFICATION_CLICK"
            },

            android=messaging.AndroidConfig(

                priority="high",

                notification=messaging.AndroidNotification(
                    channel_id="agro_channel",
                    sound="default",
                    color="#2F6A3E"
                )
            ),

            topic=data.topic
        )

        response = messaging.send(message_payload)

        # =====================================
        # STORE NOTIFICATION HISTORY
        # =====================================

        db.collection("notifications").add({

            "title": data.title,
            "body": data.body,
            "image": str(data.image) if data.image else None,
            "topic": data.topic,
            "type": data.type,
            "productId": data.id,
            "sent_by": uid,

            "timestamp":
            firestore.SERVER_TIMESTAMP
        })

        # =====================================
        # ADMIN LOG
        # =====================================

        db.collection("admin_logs").add({

            "admin_uid": uid,
            "action": "send_notification",
            "title": data.title,

            "timestamp":
            firestore.SERVER_TIMESTAMP
        })

        logging.info(
            f"Notification sent successfully by {uid}"
        )

        return {
            "success": True,
            "message_id": response
        }

    except Exception as e:

        logging.error(
            f"Notification sending failed: {str(e)}"
        )

        raise HTTPException(
            status_code=500,
            detail="Notification send failed"
        )

# =========================================
# MAIN
# =========================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 8000)
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )