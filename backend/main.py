from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from anthropic import Anthropic
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends
import time
import tempfile
import shutil

from backend.database import init_db, get_db
from backend.models import Agent, Execution, Skill
from backend.skill_service import SkillService

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

# initialize skill service
skill_service = SkillService(client)

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
    skills: List[Dict[str, Any]] = []

# Skill Management Models
class SkillCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    skill_type: str = Field(..., pattern="^(custom|anthropic)$")
    skill_id: Optional[str] = None  # For anthropic pre-built skills

class SkillResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    skill_id: str
    skill_type: str
    source_path: Optional[str]
    upload_status: str
    upload_error: Optional[str]
    created_at: str
    updated_at: str

class AgentSkillAttachRequest(BaseModel):
    skill_ids: List[int] = Field(..., min_length=1)

class AgentSkillDetachRequest(BaseModel):
    skill_ids: List[int] = Field(..., min_length=1)


##### Helper Functions #####

def build_prompt(template: str, variables: dict) -> str:
    """
    Build prompt from template by substituting variables.
    Used by both REST and WebSocket endpoints.

    Args:
        template: Prompt template with placeholders like {variable_name}
        variables: Dictionary of variable names to values

    Returns:
        Prompt string with all variables substituted
    """
    prompt = template
    for key, value in variables.items():
        prompt = prompt.replace(f"{{{key}}}", str(value))
    return prompt


###### endpoints #######
# App's root/landing page 
@app.get("/")
async def root():
    return {
        "message": "Claude Agent Control Center API",
        "version": "0.2.0",
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

    # Build prompt using helper function (supports both REST and WebSocket)
    variables = variables or {}
    prompt = build_prompt(agent.prompt_template, variables)

    start_time = time.time()

    # Check if agent has any ready skills (optional feature)
    ready_skills = [skill for skill in agent.skills if skill.upload_status == "uploaded"]

    try:
        if ready_skills:
            # Agent has skills - use beta API with skills
            skills_payload = [
                {
                    "type": skill.skill_type,  # "custom" or "anthropic"
                    "skill_id": skill.skill_id,
                    "version": "latest"
                }
                for skill in ready_skills
            ]

            message = client.beta.messages.create(
                model=agent.model,
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
                betas=["code-execution-2025-08-25", "skills-2025-10-02"],
                container={"skills": skills_payload},
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "code_execution_20250825", "name": "code_execution"}]
            )
        else:
            # No skills attached - standard API call (works perfectly fine!)
            message = client.messages.create(
                model=agent.model,
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
                messages=[{"role": "user", "content": prompt}]
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
            status = "success",
            skills_used = [s.skill_id for s in ready_skills] if ready_skills else None  # Track skills if used
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

@app.websocket("/ws/agents/{agent_id}/execute")
async def websocket_execute_agent(
    websocket: WebSocket,
    agent_id: int,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time agent execution.

    Issue #4: Basic connection and execution flow (foundation for future streaming)
    Foundation for Issue #5 (Anthropic streaming) and #6 (token tracking)

    Protocol:
    - Client sends: {"type": "execute", "variables": {...}}
    - Server sends status updates and final result
    - Connection can be reused for multiple executions
    """
    # Validate agent exists before accepting connection
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        await websocket.close(code=1008, reason="Agent not found")
        return

    # Accept WebSocket connection
    await websocket.accept()

    # Send connected message with agent info
    await websocket.send_json({
        "type": "connected",
        "agent_id": agent.id,
        "agent_name": agent.name
    })

    try:
        # Message loop - wait for execute requests
        while True:
            # 1. Receive message from client
            message = await websocket.receive_json()

            # 2. Validate message type
            if message.get("type") != "execute":
                await websocket.send_json({
                    "type": "error",
                    "error": f"Unknown message type: {message.get('type')}"
                })
                continue

            # 3. Send status update
            await websocket.send_json({
                "type": "status",
                "message": "Executing agent..."
            })

            # 4. Build prompt and execute (mirror REST logic)
            variables = message.get("variables", {})
            prompt = build_prompt(agent.prompt_template, variables)

            # Parse streaming parameters (Issue #5)
            stream_enabled = message.get("stream", False)
            stream_events = message.get("stream_events", ["text"])  # Default to text only

            # Normalize "all" to include all event types
            if "all" in stream_events:
                stream_events = ["text", "thinking", "tool_use"]

            start_time = time.time()

            # Check if agent has any ready skills (optional feature)
            ready_skills = [skill for skill in agent.skills if skill.upload_status == "uploaded"]

            try:
                # Conditional execution: streaming vs non-streaming
                if not stream_enabled:
                    # NON-STREAMING PATH (existing behavior)
                    if ready_skills:
                        # Agent has skills - use beta API with skills
                        skills_payload = [
                            {
                                "type": skill.skill_type,  # "custom" or "anthropic"
                                "skill_id": skill.skill_id,
                                "version": "latest"
                            }
                            for skill in ready_skills
                        ]

                        response = client.beta.messages.create(
                            model=agent.model,
                            max_tokens=agent.max_tokens,
                            temperature=agent.temperature,
                            betas=["code-execution-2025-08-25", "skills-2025-10-02"],
                            container={"skills": skills_payload},
                            messages=[{"role": "user", "content": prompt}],
                            tools=[{"type": "code_execution_20250825", "name": "code_execution"}]
                        )
                    else:
                        # No skills attached - standard API call (works perfectly fine!)
                        response = client.messages.create(
                            model=agent.model,
                            max_tokens=agent.max_tokens,
                            temperature=agent.temperature,
                            messages=[{"role": "user", "content": prompt}]
                        )

                    # 5. Save to database (same as REST endpoint)
                    execution_time = time.time() - start_time
                    output = response.content[0].text

                    execution = Execution(
                        agent_id=agent.id,
                        agent_name=agent.name,
                        prompt=prompt,
                        model=response.model,
                        output=output,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                        temperature=agent.temperature,
                        execution_time=execution_time,
                        status="success",
                        skills_used=[s.skill_id for s in ready_skills] if ready_skills else None
                    )
                    db.add(execution)
                    db.commit()
                    db.refresh(execution)

                    # 6. Send result to client
                    await websocket.send_json({
                        "type": "result",
                        "success": True,
                        "output": output,
                        "usage": {
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                        },
                        "model": response.model,
                        "execution_id": execution.id
                    })

                else:
                    # STREAMING PATH (Issue #5)
                    accumulated_output = ""
                    usage_info = None

                    # Determine streaming method based on skills
                    if ready_skills:
                        skills_payload = [
                            {
                                "type": skill.skill_type,
                                "skill_id": skill.skill_id,
                                "version": "latest"
                            }
                            for skill in ready_skills
                        ]

                        stream_context = client.beta.messages.stream(
                            model=agent.model,
                            max_tokens=agent.max_tokens,
                            temperature=agent.temperature,
                            betas=["code-execution-2025-08-25", "skills-2025-10-02"],
                            container={"skills": skills_payload},
                            messages=[{"role": "user", "content": prompt}],
                            tools=[{"type": "code_execution_20250825", "name": "code_execution"}]
                        )
                    else:
                        stream_context = client.messages.stream(
                            model=agent.model,
                            max_tokens=agent.max_tokens,
                            temperature=agent.temperature,
                            messages=[{"role": "user", "content": prompt}]
                        )

                    with stream_context as stream:
                        # Send stream_start (after "status" message)
                        await websocket.send_json({
                            "type": "stream_start",
                            "message_id": None,  # Will be available in final message
                            "model": agent.model
                        })

                        # Process stream events with filtering based on stream_events
                        for event in stream:
                            if event.type == "content_block_delta":
                                # Text deltas
                                if event.delta.type == "text_delta" and "text" in stream_events:
                                    # Accumulate for database
                                    accumulated_output += event.delta.text

                                    # Forward to client
                                    await websocket.send_json({
                                        "type": "content_delta",
                                        "delta_type": "text_delta",
                                        "delta": event.delta.text,
                                        "index": event.index
                                    })

                                # Thinking deltas (extended thinking)
                                elif event.delta.type == "thinking_delta" and "thinking" in stream_events:
                                    await websocket.send_json({
                                        "type": "content_delta",
                                        "delta_type": "thinking_delta",
                                        "delta": event.delta.thinking,
                                        "index": event.index
                                    })

                                # Tool use JSON deltas
                                elif event.delta.type == "input_json_delta" and "tool_use" in stream_events:
                                    await websocket.send_json({
                                        "type": "content_delta",
                                        "delta_type": "input_json_delta",
                                        "delta": event.delta.partial_json,
                                        "index": event.index
                                    })

                            elif event.type == "message_delta":
                                # Capture final usage info (cumulative)
                                if hasattr(event, 'usage') and event.usage:
                                    usage_info = {
                                        "output_tokens": event.usage.output_tokens
                                    }

                        # Get final message after stream closes
                        final_message = stream.get_final_message()

                        # Complete usage info with input tokens
                        if usage_info:
                            usage_info["input_tokens"] = final_message.usage.input_tokens
                            usage_info["total_tokens"] = final_message.usage.input_tokens + usage_info["output_tokens"]
                        else:
                            usage_info = {
                                "input_tokens": final_message.usage.input_tokens,
                                "output_tokens": final_message.usage.output_tokens,
                                "total_tokens": final_message.usage.input_tokens + final_message.usage.output_tokens
                            }

                        # Send stream_end
                        await websocket.send_json({
                            "type": "stream_end",
                            "stop_reason": final_message.stop_reason,
                            "usage": usage_info
                        })

                        # Use accumulated_output for database save
                        output = accumulated_output
                        execution_time = time.time() - start_time

                        # Save to database
                        execution = Execution(
                            agent_id=agent.id,
                            agent_name=agent.name,
                            prompt=prompt,
                            model=final_message.model,
                            output=output,
                            input_tokens=final_message.usage.input_tokens,
                            output_tokens=final_message.usage.output_tokens,
                            total_tokens=final_message.usage.input_tokens + final_message.usage.output_tokens,
                            temperature=agent.temperature,
                            execution_time=execution_time,
                            status="success",
                            skills_used=[s.skill_id for s in ready_skills] if ready_skills else None
                        )
                        db.add(execution)
                        db.commit()
                        db.refresh(execution)

                        # Send final result message (backward compatibility)
                        await websocket.send_json({
                            "type": "result",
                            "success": True,
                            "output": output,
                            "usage": usage_info,
                            "model": final_message.model,
                            "execution_id": execution.id
                        })

            except Exception as e:
                # Log failed execution to database
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
                db.refresh(execution)

                # Send error to client
                await websocket.send_json({
                    "type": "error",
                    "error": str(e),
                    "execution_id": execution.id
                })

    except WebSocketDisconnect:
        # Client disconnected gracefully - no action needed
        pass
    except Exception as e:
        # Unexpected error - attempt to close connection gracefully
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass

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


##### Skill Management Endpoints #####

@app.post("/skills/custom", response_model=SkillResponse)
async def create_custom_skill(
    name: str,
    skill_directory: UploadFile = File(...),
    description: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Upload a custom skill from a ZIP file containing skill directory.

    Expected: ZIP file with skill implementation (must contain SKILL.md)
    """
    try:
        # Save uploaded zip to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "skill.zip")
            with open(zip_path, "wb") as buffer:
                shutil.copyfileobj(skill_directory.file, buffer)

            # Extract zip
            extract_dir = os.path.join(temp_dir, "extracted")
            shutil.unpack_archive(zip_path, extract_dir)

            # Upload skill
            skill = skill_service.upload_custom_skill(
                name=name,
                description=description,
                skill_dir_path=extract_dir,
                db=db
            )

            return SkillResponse(**skill.to_dict())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/skills/anthropic", response_model=SkillResponse)
async def register_anthropic_skill(
    request: SkillCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Register a pre-built Anthropic skill (pptx, xlsx, docx, pdf).

    Request body should include:
    - name: Display name
    - skill_id: One of: pptx, xlsx, docx, pdf
    - description: Optional description
    """
    if not request.skill_id:
        raise HTTPException(status_code=400, detail="skill_id is required for Anthropic skills")

    try:
        skill = skill_service.register_anthropic_skill(
            name=request.name,
            skill_id=request.skill_id,
            description=request.description,
            db=db
        )
        return SkillResponse(**skill.to_dict())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills", response_model=List[SkillResponse])
async def list_skills(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all registered skills in the database."""
    skills = db.query(Skill).offset(skip).limit(limit).all()
    return [SkillResponse(**skill.to_dict()) for skill in skills]


@app.get("/skills/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: int, db: Session = Depends(get_db)):
    """Get a specific skill by ID."""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(**skill.to_dict())


@app.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    """Delete a skill (only if not attached to any agents)."""
    try:
        skill_service.delete_skill(skill_id, db)
        return {"message": "Skill deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


##### Agent-Skill Association Endpoints #####

@app.post("/agents/{agent_id}/skills/attach")
async def attach_skills_to_agent(
    agent_id: int,
    request: AgentSkillAttachRequest,
    db: Session = Depends(get_db)
):
    """Attach one or more skills to an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        attached_skills = skill_service.attach_skills_to_agent(
            agent=agent,
            skill_ids=request.skill_ids,
            db=db
        )
        return {
            "message": f"Attached {len(attached_skills)} skill(s) to agent '{agent.name}'",
            "skills": [s.to_dict() for s in attached_skills]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agents/{agent_id}/skills/detach")
async def detach_skills_from_agent(
    agent_id: int,
    request: AgentSkillDetachRequest,
    db: Session = Depends(get_db)
):
    """Detach one or more skills from an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        detached_count = skill_service.detach_skills_from_agent(
            agent=agent,
            skill_ids=request.skill_ids,
            db=db
        )
        return {"message": f"Detached {detached_count} skill(s) from agent '{agent.name}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents/{agent_id}/skills", response_model=List[SkillResponse])
async def get_agent_skills(agent_id: int, db: Session = Depends(get_db)):
    """Get all skills attached to an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return [SkillResponse(**skill.to_dict()) for skill in agent.skills]


# health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}