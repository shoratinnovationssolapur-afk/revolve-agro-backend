import firebase_admin
from firebase_admin import credentials, messaging
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

# 🔥 Use the NEW Revolve Agro Service Account JSON
cred = credentials.Certificate("revolveagro-firebase-adminsdk.json")
firebase_admin.initialize_app(cred)

@app.get("/")
def read_root():
    return {"status": "Revolve Agro Backend Active"}

@app.post("/send-agro-notification")
async def send_agro_notification(request: Request):
    body = await request.json()

    title = body.get("title", "Revolve Agro Update")
    message = body.get("body", "New stock or update available!")
    image = body.get("image")
    # Using the unique topic we set in your Flutter main.dart
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
    uvicorn.run(app, host="0.0.0.0", port=8000)