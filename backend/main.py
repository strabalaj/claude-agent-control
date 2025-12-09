from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends
import time

from backend.database import init_db, get_db
from backend.models import Agent, Execution

# Now get me them environmental vars
load_dotenv()

# initialize FastAPI 
app = FastAPI(title="Claude Agent Control Center")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# initialize anthropic client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# initialzie db on starup
@app.on_event("startup")
async def startup_event():
    init_db()

##### Pydantic Models #####

# Req model
class AgentExecuteRequest(BaseModel):
    prompt: str
    model: str = "claude-sonnet-4-5"  
    max_tokens: int = 5000
    temperature: float = 1.0

# Resp model
class AgentExecuteResponse (BaseModel):
    success: bool
    output: str
    usage: dict
    model: str
    execution_id : Optional[int] = None
    error: Optional[str] = None

class AgentCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    prompt_template: str
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 5000
    temperature: float = 1.0

class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt_template: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None

class AgentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    prompt_template: str
    model: str
    max_tokens: int
    temperature: float
    created_at: str
    updated_at: str



###### endpoints #######
# App's root/landing page 
@app.get("/")
async def root():
    return {
        "message": "Claude Agent Control Center API",
        "version": "0.1.1",
        "status": "running"
    }

# main agent execution endpoint
@app.post("/execute", response_model=AgentExecuteResponse)
async def execute_agent(
    request: AgentExecuteRequest,
    db: Session = Depends(get_db)):
    
    start_time = time.time()

    try:
        message = client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=[
                {"role": "user", "content": request.prompt}
            ]
        )

        #grab execution time
        execution_time = time.time() - start_time
        # extract the response from Claude
        claude_output = message.content[0].text

        #save execution to db
        execution = Execution(
            agent_id = None,
            agent_name = None,
            prompt = request.prompt,
            model = message.model,
            output = claude_output,
            input_tokens = message.usage.input_tokens,
            output_tokens = message.usage.output_tokens,
            total_tokens = message.usage.input_tokens + message.usage.output_tokens,
            temperature = request.temperature,
            execution_time = execution_time,
            status = "success"
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)


        response = AgentExecuteResponse(
            success=True,
            output=claude_output,
            usage={
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "total_tokens": message.usage.input_tokens + message.usage.output_tokens
            },
            model=message.model,
            execution_id = execution.id
        )

        return response

    except Exception as e:
        execution_time = time.time() - start_time
        
        #capturing failed execution
        execution = Execution(
            agent_id=None,
            agent_name=None,
            prompt=request.prompt,
            model=request.model,
            output="",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            temperature=request.temperature,
            execution_time=execution_time,
            status="failed",
            error_message=str(e)
        )
        db.add(execution)
        db.commit()


##### Agent CRUD Endpoints ####

@app.post("/agents", response_model = AgentResponse)
async def create_agent(agent: AgentCreateRequest,db: Session = Depends(get_db)):
    #check to see if agent name already exists
    existing = db.query(Agent).filter(Agent.name == agent.name).first()
    if existing:
        raise HTTPException(
            status_code = 400,
            detail = f"Agent with name '{agent.name}' already exists"
        )

    db_agent = Agent(
        name = agent.name,
        description = agent.description,
        prompt_template = agent.prompt_template,
        model = agent.model,
        max_tokens = agent.max_tokens,
        temperature = agent.temperature
    )

    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)

    return AgentResponse(**db_agent.to_dict())

@app.get("/agents", response_model = List[AgentResponse])
async def list_agents(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    agents = db.query(Agent).offset(skip).limit(limit).all()
    return [AgentResponse(**agent.to_dict()) for agent in agents]

@app.get("/agents/{agent_id}", response_model = AgentResponse)
async def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code = 404, detail = "Agent not found")

    return AgentResponse(**agent.to_dict())

@app.put("/agents/{agent_id}", response_model = AgentResponse)
async def update_agent(agent_id: int, agent_update: AgentUpdateRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent was not found")
    update_data = agent_update.dict(exclude_unset = True)
    for field, value in update_data.items():
        setattr(agent, field, value)
    
    db.commit()
    db.refresh(agent)

    return AgentResponse(**agent.to_dict())

@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code = 404, detail = "Agent was not found")
    db.delete(agent)
    db.commit()

    return {"message": f"Agent '{agent.name}' was deleted successfully"}

@app.post("/agents/{agent_id}/execute", response_model = AgentExecuteResponse)
async def execute_saved_agent(agent_id: int, variables: Optional[dict] = None, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code = 404, detail = "Agent was not found ")
    
    prompt = agent.prompt_template
    if variables:
        for key, value in variables.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))
    
    start_time = time.time()

    try:
        message = client.messages.create(
            model = agent.model, 
            max_tokens = agent.max_tokens,
            temperature = agent.temperature,
            messages = [{"role" : "user", "content": prompt}]
        )
        execution_time = time.time() - start_time
        claude_output = message.content[0].text

        #save that execution
        execution = Execution(
            agent_id = agent.id,
            agent_name = agent.name,
            prompt = prompt,
            model = message.model,
            output = claude_output,
            input_tokens = message.usage.input_tokens,
            output_tokens = message.usage.output_tokens,
            total_tokens = message.usage.input_tokens + message.usage.output_tokens,
            temperature = agent.temperature,
            execution_time = execution_time,
            status = "success"
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        return AgentExecuteResponse(
            success = True,
            output = claude_output,
            usage = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "total_tokens": message.usage.input_tokens + message.usage.output_tokens
            },
            model = message.model,
            execution_id = execution.id
        )
    except Exception as e:
        execution_time = time.time() - start_time
        
        execution = Execution(
            agent_id=agent.id,
            agent_name=agent.name,
            prompt=prompt,
            model=agent.model,
            output="",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            temperature=agent.temperature,
            execution_time=execution_time,
            status="failed",
            error_message=str(e)
        )
        db.add(execution)
        db.commit()
        
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}"
        )

@app.get("/executions")
async def list_executions(skip: int = 0, limit: int = 50, agent_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Execution)
    if agent_id is not None:
        query = query.filter(Execution.agent_id == agent_id)
    executions = query.order_by(Execution.created_at.desc()).offset(skip).limit(limit).all()

    return [execution.to_dict() for execution in executions]

@app.get("/executions/{execution_id}")
async def get_execution( execution_id: int, db: Session = Depends(get_db)):
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code = 404, detail = "Execution was not found")

    return execution.to_dict()

# health check 
@app.get("/health")
async def health_check():
    return {"status": "healthy"}