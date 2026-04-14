import os
import json
import firebase_admin
from firebase_admin import credentials, messaging
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

# 🛡️ Initialize Firebase with Environment Variable
# Make sure your Render Env Var name matches this: FIREBASE_SERVICE_ACCOUNT
service_account_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

if service_account_str and not firebase_admin._apps:
    try:
        cred_json = json.loads(service_account_str)
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized successfully for Revolve Agro")
    except Exception as e:
        print(f"❌ Failed to initialize Firebase: {e}")
elif not service_account_str:
    print("⚠️ Warning: FIREBASE_SERVICE_ACCOUNT environment variable is not set!")

@app.get("/")
def read_root():
    return {"status": "Revolve Agro Backend Active", "project": "revolveagro-9e98e"}

@app.post("/send-agro-notification")
async def send_agro_notification(request: Request):
    body = await request.json()

    title = body.get("title", "Revolve Agro Update")
    message = body.get("body", "New stock or update available!")
    image = body.get("image")
    
    # Matches your Flutter main.dart subscription
    topic = "agro_members" 
    
    notif_type = body.get("type", "simple") 
    product_id = body.get("id", "")

    message_payload = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=message,
            image=image
        ),
        data={
            "type": notif_type,
            "productId": product_id,
            "click_action": "FLUTTER_NOTIFICATION_CLICK"
        },
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id="agro_channel", # Matches your Flutter code
                sound="default",
                color="#2F6A3E"
            )
        ),
        topic=topic
    )

    try:
        response = messaging.send(message_payload)
        return {"success": True, "message_id": response, "topic": topic}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Render uses the PORT environment variable
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)