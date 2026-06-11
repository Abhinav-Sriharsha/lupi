import { Room } from 'livekit-client';

const url = 'wss://interview-rzeidzn1.livekit.cloud';
const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiQ3VzdG9tZXIiLCJ2aWRlbyI6eyJyb29tSm9pbiI6dHJ1ZSwicm9vbSI6Imx1cGktMTc4MTE0NTk0NSIsImNhblB1Ymxpc2giOnRydWUsImNhblN1YnNjcmliZSI6dHJ1ZSwiY2FuUHVibGlzaERhdGEiOnRydWV9LCJzdWIiOiJ1bmtub3duIiwiaXNzIjoiQVBJejhFd2hjSFQ5QUpEIiwibmJmIjoxNzgxMTQ1OTQ1LCJleHAiOjE3ODExNjc1NDV9.zH2Xf6NSYkxE0PRCmSCHVAA3hWvJmsyOXdUJ7BTr_4g';

async function test() {
  const room = new Room();
  try {
    await room.connect(url, token);
    console.log("Connected successfully!");
    room.disconnect();
  } catch (e) {
    console.error("Connection failed!");
    console.error(e);
  }
}

test();
