from fastapi import FastAPI, HTTPException, UploadFile, File
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

    # Check if agent has any ready skills (optional feature)
    skill_ids = [skill.skill_id for skill in agent.skills if skill.upload_status == "uploaded"]

    try:
        if skill_ids:
            # Agent has skills - use beta API with skills
            message = client.messages.create(
                model=agent.model,
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
                messages=[{"role": "user", "content": prompt}],
                betas=["code-execution-2025-08-25", "skills-2025-10-02"],
                container={
                    "skills": [{"type": "skill", "id": sid} for sid in skill_ids]
                }
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
            skills_used = skill_ids if skill_ids else None  # Track skills if used
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