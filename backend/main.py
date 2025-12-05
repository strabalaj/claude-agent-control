from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
import os
from dotenv import load_dotenv

# Now get me them environmental vars
load_dotenv()

# Initialize FastAPI 
app = FastAPI(title="Claude Agent Control Center")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize anthropic client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Request model
class AgentRequest(BaseModel):
    prompt: str
    model: str = "claude-sonnet-4-5"  # ✅ Fixed
    max_tokens: int = 4096
    temperature: float = 1.0

# Response model
class AgentResponse(BaseModel):
    success: bool
    output: str
    usage: dict
    model: str
    error: str | None = None

# Application root
@app.get("/")
async def root():
    return {
        "message": "Claude Agent Control Center API",
        "version": "0.1.0",
        "status": "running"
    }

# Main agent execution endpoint
@app.post("/execute", response_model=AgentResponse)
async def execute_agent(request: AgentRequest):
    try:
        message = client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=[
                {"role": "user", "content": request.prompt}
            ]
        )

        # Extract response from Claude
        claude_output = message.content[0].text

        response = AgentResponse(
            success=True,
            output=claude_output,
            usage={
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "total_tokens": message.usage.input_tokens + message.usage.output_tokens
            },
            model=message.model
        )

        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}"
        )

# Health check 
@app.get("/health")
async def health_check():
    return {"status": "healthy"}