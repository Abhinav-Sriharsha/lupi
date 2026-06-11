import asyncio
import os
from livekit import rtc

async def main():
    room = rtc.Room()
    url = "wss://interview-rzeidzn1.livekit.cloud"
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiQ3VzdG9tZXIiLCJ2aWRlbyI6eyJyb29tSm9pbiI6dHJ1ZSwicm9vbSI6Imx1cGktMTc4MTE0NTk0NSIsImNhblB1Ymxpc2giOnRydWUsImNhblN1YnNjcmliZSI6dHJ1ZSwiY2FuUHVibGlzaERhdGEiOnRydWV9LCJzdWIiOiJ1bmtub3duIiwiaXNzIjoiQVBJejhFd2hjSFQ5QUpEIiwibmJmIjoxNzgxMTQ1OTQ1LCJleHAiOjE3ODExNjc1NDV9.zH2Xf6NSYkxE0PRCmSCHVAA3hWvJmsyOXdUJ7BTr_4g"
    try:
        await room.connect(url, token)
        print("Connected successfully!")
        await room.disconnect()
    except Exception as e:
        print(f"Connection failed: {e}")

asyncio.run(main())
