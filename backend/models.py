from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON, Table, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()

# Association table for many-to-many relationship between agents and skills
agent_skills_association = Table(
    'agent_skills',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('agent_id', Integer, ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
    Column('skill_id', Integer, ForeignKey('skills.id', ondelete='CASCADE'), nullable=False),
    Column('created_at', DateTime, default=datetime.utcnow),
    UniqueConstraint('agent_id', 'skill_id', name='unique_agent_skill')
)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    skill_id = Column(String(255), nullable=False, unique=True, index=True)  # Claude API skill_id
    skill_type = Column(String(50), nullable=False)  # 'custom' or 'anthropic'
    source_path = Column(Text, nullable=True)  # Local directory path for custom skills
    upload_status = Column(String(50), default='pending')  # 'pending', 'uploaded', 'failed'
    upload_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to agents
    agents = relationship('Agent', secondary=agent_skills_association, back_populates='skills')

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "source_path": self.source_path,
            "upload_status": self.upload_status,
            "upload_error": self.upload_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key = True, index = True)
    name = Column(String(100), nullable = False, unique = True, index = True)
    description = Column(Text, nullable = True)
    prompt_template = Column(Text, nullable = False)
    model = Column(String(99), default = "claude-sonnet-4-5")
    max_tokens = Column(Integer, default = 5000)
    temperature = Column(Float, default = 1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to skills
    skills = relationship('Skill', secondary=agent_skills_association, back_populates='agents')

    #convery agent table to JSON friendly dictionary!
    def to_dict (self):
        return {
            "id" : self.id,
            "name" : self.name,
            "description" : self.description,
            "prompt_template" : self.prompt_template,
            "model" : self.model,
            "max_tokens" : self.max_tokens,
            "temperature" : self.temperature,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "skills": [{"id": s.id, "name": s.name, "skill_id": s.skill_id, "skill_type": s.skill_type} for s in self.skills]
        }


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key = True, index = True)
    agent_id = Column(Integer, nullable = True, index = True)
    agent_name = Column(String(100), nullable = True)
    prompt = Column(Text, nullable = False)
    model = Column(String(100), nullable = False)
    output = Column(Text, nullable = False)
    input_tokens = Column(Integer, nullable = False)
    output_tokens = Column(Integer, nullable = False)
    total_tokens = Column(Integer, nullable = False)
    temperature = Column(Float, nullable = False)
    execution_time = Column(Float, nullable=True)
    status = Column(String(50), default = "success")
    error_message = Column(Text, nullable =True)
    skills_used = Column(JSON, nullable=True)  # Track which skills were used in this execution
    created_at = Column(DateTime, default = datetime.utcnow, index = True)

    def to_dict(self):
        return {
            "id" : self.id,
            "agent_id" : self.agent_id,
            "agent_name" : self.agent_name,
            "prompt" : self.prompt,
            "model" : self.model,
            "output" : self.output,
            "input_tokens" : self.input_tokens,
            "output_tokens" : self.output_tokens,
            "total_tokens": self.total_tokens,
            "temperature" : self.temperature,
            "execution_time" : self.execution_time,
            "status": self.status,
            "error_message" : self.error_message,
            "skills_used": self.skills_used,
            "created_at" : self.created_at.isoformat() if self.created_at else None,
        }