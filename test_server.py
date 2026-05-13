# test_server.py - Minimal working test
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def home():
    return "<h1 style='font-family:sans-serif;text-align:center;padding:50px'>🐄 PashuMitra AI is LIVE!<br><br><a href='/api/diagnose?text=bukhar&type=text'>🔗 Test AI: bukhar</a></h1>"

@app.get("/api/diagnose")
def diagnose(text: str = "test", type: str = "text"):
    return {"status": "ok", "you_sent": text, "type": type, "message": "AI working! 🎉"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8550)