from anthropic import Anthropic
from sqlalchemy.orm import Session
from backend.models import Skill, Agent
from typing import Optional, List
import os
from pathlib import Path
import tempfile
import shutil


class SkillService:
    """
    Service layer for Claude Agent Skills management.
    Handles skill upload, validation, and Claude API interactions.

    Follows Single Responsibility Principle by separating skill management
    logic from the HTTP/API layer.
    """

    def __init__(self, anthropic_client: Anthropic):
        """
        Initialize SkillService with Anthropic client.

        Args:
            anthropic_client: Authenticated Anthropic client instance
        """
        self.client = anthropic_client
        self.skills_storage_path = Path(__file__).parent.parent / "data" / "skills"
        self.skills_storage_path.mkdir(exist_ok=True)

    def upload_custom_skill(
        self,
        name: str,
        description: Optional[str],
        skill_dir_path: str,
        db: Session
    ) -> Skill:
        """
        Uploads a custom skill directory to Claude API.

        Args:
            name: Skill name (must be unique)
            description: Optional skill description
            skill_dir_path: Path to skill directory on filesystem
            db: Database session

        Returns:
            Skill: Created skill database record

        Raises:
            ValueError: If skill directory doesn't exist or upload fails
        """
        if not os.path.exists(skill_dir_path):
            raise ValueError(f"Skill directory not found: {skill_dir_path}")

        # Check if skill name already exists
        existing = db.query(Skill).filter(Skill.name == name).first()
        if existing:
            raise ValueError(f"Skill with name '{name}' already exists")

        # Create pending skill record
        skill = Skill(
            name=name,
            description=description,
            skill_type="custom",
            skill_id="",  # Will be set after upload
            source_path=skill_dir_path,
            upload_status="pending"
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)

        try:
            # Upload to Claude API
            from anthropic.lib import files_from_dir

            uploaded_skill = self.client.beta.skills.create(
                display_title=name,
                files=files_from_dir(skill_dir_path),
                betas=["skills-2025-10-02"]
            )

            # Update skill record with API response
            skill.skill_id = uploaded_skill.id
            skill.upload_status = "uploaded"
            db.commit()
            db.refresh(skill)

            return skill

        except Exception as e:
            # Update skill record with error
            skill.upload_status = "failed"
            skill.upload_error = str(e)
            db.commit()
            raise ValueError(f"Skill upload failed: {str(e)}")

    def register_anthropic_skill(
        self,
        name: str,
        skill_id: str,
        description: Optional[str],
        db: Session
    ) -> Skill:
        """
        Registers a pre-built Anthropic skill (pptx, xlsx, docx, pdf).

        Args:
            name: Skill display name (e.g., "PDF Processor")
            skill_id: Anthropic skill ID (e.g., "pptx", "xlsx", "docx", "pdf")
            description: Optional description
            db: Database session

        Returns:
            Skill: Created skill database record

        Raises:
            ValueError: If skill_id is invalid or already registered
        """
        # Validate skill_id format
        valid_anthropic_skills = ["pptx", "xlsx", "docx", "pdf"]
        if skill_id not in valid_anthropic_skills:
            raise ValueError(
                f"Invalid Anthropic skill_id '{skill_id}'. "
                f"Must be one of: {', '.join(valid_anthropic_skills)}"
            )

        # Check if skill name already exists
        existing_name = db.query(Skill).filter(Skill.name == name).first()
        if existing_name:
            raise ValueError(f"Skill with name '{name}' already exists")

        # Check if this Anthropic skill is already registered
        existing_skill = db.query(Skill).filter(Skill.skill_id == skill_id).first()
        if existing_skill:
            raise ValueError(
                f"Anthropic skill '{skill_id}' is already registered as '{existing_skill.name}'"
            )

        # Create skill record
        skill = Skill(
            name=name,
            description=description,
            skill_id=skill_id,
            skill_type="anthropic",
            upload_status="uploaded"  # Pre-built skills don't need upload
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)

        return skill

    def attach_skills_to_agent(
        self,
        agent: Agent,
        skill_ids: List[int],
        db: Session
    ) -> List[Skill]:
        """
        Attaches skills to an agent.

        Args:
            agent: Agent to attach skills to
            skill_ids: List of skill database IDs to attach
            db: Database session

        Returns:
            List[Skill]: List of newly attached skills

        Raises:
            ValueError: If any skill_id is invalid or skill upload failed
        """
        attached_skills = []

        for skill_id in skill_ids:
            skill = db.query(Skill).filter(Skill.id == skill_id).first()

            if not skill:
                raise ValueError(f"Skill with ID {skill_id} not found")

            if skill.upload_status != "uploaded":
                raise ValueError(
                    f"Skill '{skill.name}' is not ready (status: {skill.upload_status})"
                )

            # Add skill if not already attached
            if skill not in agent.skills:
                agent.skills.append(skill)
                attached_skills.append(skill)

        db.commit()
        db.refresh(agent)

        return attached_skills

    def detach_skills_from_agent(
        self,
        agent: Agent,
        skill_ids: List[int],
        db: Session
    ) -> int:
        """
        Detaches skills from an agent.

        Args:
            agent: Agent to detach skills from
            skill_ids: List of skill database IDs to detach
            db: Database session

        Returns:
            int: Number of skills actually detached
        """
        detached_count = 0

        for skill_id in skill_ids:
            skill = db.query(Skill).filter(Skill.id == skill_id).first()
            if skill and skill in agent.skills:
                agent.skills.remove(skill)
                detached_count += 1

        db.commit()
        db.refresh(agent)

        return detached_count

    def list_claude_skills(self) -> List[dict]:
        """
        Lists all skills from Claude API.

        Returns:
            List[dict]: List of skills from Claude API

        Raises:
            ValueError: If API request fails
        """
        try:
            skills = self.client.beta.skills.list(
                betas=["skills-2025-10-02"]
            )
            return [
                {
                    "id": s.id,
                    "title": s.display_title if hasattr(s, 'display_title') else s.id,
                    "type": s.type if hasattr(s, 'type') else "unknown"
                }
                for s in skills.data
            ]
        except Exception as e:
            raise ValueError(f"Failed to list Claude skills: {str(e)}")

    def delete_skill(self, skill_id: int, db: Session) -> None:
        """
        Deletes a skill (only if not attached to any agents).

        Args:
            skill_id: Database ID of skill to delete
            db: Database session

        Raises:
            ValueError: If skill is attached to agents or doesn't exist
        """
        skill = db.query(Skill).filter(Skill.id == skill_id).first()

        if not skill:
            raise ValueError(f"Skill with ID {skill_id} not found")

        # Check if skill is attached to any agents
        if len(skill.agents) > 0:
            raise ValueError(
                f"Cannot delete skill '{skill.name}' - it is attached to "
                f"{len(skill.agents)} agent(s). Detach it first."
            )

        db.delete(skill)
        db.commit()
