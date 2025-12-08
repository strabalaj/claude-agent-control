from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

Base = declarative_base ()


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
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
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
            "created_at" : self.created_at.isoformat() if self.created_at else None,
        }