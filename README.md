# Claude Agent Control Center

A fullstack Python application for creating, monitoring, and managing Claude AI agents with Agent Skills support.

## Features

### Core Agent Management
- **Create & Manage Agents**: Define reusable Claude agents with custom prompt templates
- **Variable Substitution**: Dynamic prompt templates with variable placeholders (e.g., `{variable_name}`)
- **Execution History**: Track all agent executions with token usage and performance metrics
- **Full CRUD Operations**: Create, read, update, and delete agents via REST API

### Agent Skills (NEW!)
- **Custom Skills**: Upload your own skill directories to extend Claude's capabilities
- **Pre-built Skills**: Register Anthropic's pre-built skills (PDF, PowerPoint, Excel, Word)
- **Skill-Agent Association**: Attach multiple skills to agents for enhanced functionality
- **Optional Enhancement**: Skills are completely optional - agents work perfectly without them
- **Automatic Integration**: When skills are attached, they're automatically used during execution

## Tech Stack

- **Backend**: FastAPI (Python 3.14+)
- **Database**: SQLAlchemy + SQLite
- **AI**: Anthropic Claude API with Skills beta support
- **Package Manager**: uv

## Project Structure

```
claude-agent-control/
├── backend/
│   ├── main.py              # FastAPI application with all endpoints
│   ├── models.py            # SQLAlchemy models (Agent, Skill, Execution)
│   ├── database.py          # Database configuration
│   └── skill_service.py     # Service layer for skill management
├── data/
│   ├── agents.db            # SQLite database
│   └── skills/              # Storage for uploaded custom skills
├── pyproject.toml           # Project dependencies
└── README.md                # This file
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd claude-agent-control
   ```

2. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Install dependencies**:
   ```bash
   uv sync
   ```

4. **Set up environment variables**:
   Create a `.env` file with your Anthropic API key:
   ```bash
   ANTHROPIC_API_KEY=your_api_key_here
   ```

## Running the Application

Start the server:
```bash
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

View API documentation: `http://localhost:8000/docs`

## API Endpoints

### Agent Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | List all agents |
| GET | `/agents/{agent_id}` | Get specific agent (includes attached skills) |
| POST | `/agents` | Create new agent |
| PUT | `/agents/{agent_id}` | Update agent |
| DELETE | `/agents/{agent_id}` | Delete agent |
| POST | `/agents/{agent_id}/execute` | Execute agent with optional variables |

### WebSocket Real-Time Execution

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws/agents/{agent_id}/execute` | Real-time agent execution with status updates |

**Message Protocol:**
- **Client → Server**: `{"type": "execute", "variables": {...}}`
- **Server → Client**: Status updates, results, and errors as JSON messages

**Connection Flow:**
1. Connect to WebSocket endpoint
2. Receive `connected` message with agent info
3. Send `execute` request with optional variables
4. Receive `status` updates during execution
5. Receive `result` (success) or `error` (failure) message
6. Connection stays open for multiple executions

### Skill Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/skills` | List all skills |
| GET | `/skills/{skill_id}` | Get specific skill |
| POST | `/skills/custom` | Upload custom skill (ZIP file) |
| POST | `/skills/anthropic` | Register Anthropic pre-built skill |
| DELETE | `/skills/{skill_id}` | Delete skill (if not in use) |

### Agent-Skill Association

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents/{agent_id}/skills` | List skills attached to agent |
| POST | `/agents/{agent_id}/skills/attach` | Attach skills to agent |
| POST | `/agents/{agent_id}/skills/detach` | Detach skills from agent |

### Execution History

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/executions` | List all executions (supports filtering by agent_id) |
| GET | `/executions/{execution_id}` | Get specific execution |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |

## Usage Examples

### 1. Create an Agent

```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Document Analyzer",
    "description": "Analyzes PDF documents",
    "prompt_template": "Analyze this document: {document_name}",
    "model": "claude-sonnet-4-5"
  }'
```

### 2. Register an Anthropic Skill

```bash
curl -X POST http://localhost:8000/skills/anthropic \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PDF Processor",
    "skill_id": "pdf",
    "skill_type": "anthropic",
    "description": "Process and analyze PDF documents"
  }'
```

### 3. Attach Skill to Agent

```bash
curl -X POST http://localhost:8000/agents/1/skills/attach \
  -H "Content-Type: application/json" \
  -d '{"skill_ids": [1]}'
```

### 4. Execute Agent (with or without skills)

```bash
# Agent will automatically use attached skills if any
curl -X POST http://localhost:8000/agents/1/execute \
  -H "Content-Type: application/json" \
  -d '{"document_name": "financial_report.pdf"}'
```

### 5. Upload Custom Skill

```bash
# First, create a skill directory with SKILL.md
mkdir my-custom-skill
echo "---
name: my-skill
description: My custom skill
---
# My Custom Skill
Instructions here..." > my-custom-skill/SKILL.md

# Zip it
zip -r my-skill.zip my-custom-skill/

# Upload via API
curl -X POST http://localhost:8000/skills/custom \
  -F "name=My Custom Skill" \
  -F "skill_directory=@my-skill.zip"
```

### 6. WebSocket Real-Time Execution (Python)

```python
import asyncio
import websockets
import json

async def execute_agent_websocket():
    uri = "ws://localhost:8000/ws/agents/1/execute"

    async with websockets.connect(uri) as ws:
        # 1. Receive connected message
        connected = json.loads(await ws.recv())
        print(f"Connected to agent: {connected['agent_name']}")

        # 2. Send execute request
        await ws.send(json.dumps({
            "type": "execute",
            "variables": {"document_name": "report.pdf"}
        }))

        # 3. Receive messages (status updates and result)
        async for message in ws:
            data = json.loads(message)

            if data['type'] == 'status':
                print(f"Status: {data['message']}")

            elif data['type'] == 'result':
                print(f"Output: {data['output']}")
                print(f"Tokens: {data['usage']['total_tokens']}")
                print(f"Execution ID: {data['execution_id']}")
                break

            elif data['type'] == 'error':
                print(f"Error: {data['error']}")
                break

asyncio.run(execute_agent_websocket())
```

### 7. WebSocket Real-Time Execution (TypeScript)

```typescript
interface WSMessage {
  type: 'connected' | 'status' | 'result' | 'error';
  agent_id?: number;
  agent_name?: string;
  message?: string;
  output?: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  model?: string;
  execution_id?: number;
  error?: string;
}

const ws = new WebSocket('ws://localhost:8000/ws/agents/1/execute');

ws.onmessage = (event: MessageEvent) => {
  const data: WSMessage = JSON.parse(event.data);

  switch(data.type) {
    case 'connected':
      console.log(`Connected to agent: ${data.agent_name}`);
      // Send execute request
      ws.send(JSON.stringify({
        type: 'execute',
        variables: { document_name: 'report.pdf' }
      }));
      break;

    case 'status':
      console.log(`Status: ${data.message}`);
      break;

    case 'result':
      console.log(`Output: ${data.output}`);
      console.log(`Tokens: ${data.usage?.total_tokens}`);
      console.log(`Execution ID: ${data.execution_id}`);
      break;

    case 'error':
      console.error(`Error: ${data.error}`);
      break;
  }
};

ws.onerror = (error: Event) => {
  console.error('WebSocket error:', error);
};
```

### 8. Testing WebSocket Endpoint

```bash
# Install websockets library
uv add --dev websockets

# Run test script
python test_websocket.py
```

## Database Schema

### Agents Table
- **id**: Primary key
- **name**: Unique agent name
- **description**: Optional description
- **prompt_template**: Template with variable placeholders
- **model**: Claude model version
- **max_tokens**: Token limit
- **temperature**: Sampling temperature
- **created_at**, **updated_at**: Timestamps

### Skills Table
- **id**: Primary key
- **name**: Unique skill name
- **description**: Optional description
- **skill_id**: Claude API skill ID
- **skill_type**: 'custom' or 'anthropic'
- **source_path**: Local path (for custom skills)
- **upload_status**: 'pending', 'uploaded', or 'failed'
- **upload_error**: Error message if upload failed
- **created_at**, **updated_at**: Timestamps

### Agent_Skills Table (Many-to-Many)
- **id**: Primary key
- **agent_id**: Foreign key to agents
- **skill_id**: Foreign key to skills
- **created_at**: Timestamp

### Executions Table
- **id**: Primary key
- **agent_id**, **agent_name**: Tracking
- **prompt**: Actual prompt sent
- **model**: Model used
- **output**: Claude's response
- **input_tokens**, **output_tokens**, **total_tokens**: Usage stats
- **temperature**: Temperature used
- **execution_time**: Duration in seconds
- **status**: 'success' or 'failed'
- **error_message**: Error details if failed
- **skills_used**: JSON array of skill IDs used
- **created_at**: Timestamp

## Agent Skills Information

### What are Agent Skills?

Agent Skills are modular, reusable capabilities that extend Claude's functionality:

- **Model-invoked**: Claude automatically decides when to use them based on the task
- **Progressive disclosure**: Only loads what's needed, when it's needed
- **Cloud-based**: Uploaded to Claude's servers, persist across sessions
- **Optional**: Agents work perfectly fine without skills - they're an enhancement

### Available Anthropic Pre-built Skills

- **pdf**: Process and analyze PDF documents
- **pptx**: Create and modify PowerPoint presentations
- **xlsx**: Work with Excel spreadsheets
- **docx**: Handle Word documents

### Creating Custom Skills

Custom skills must include a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: your-skill-name
description: What this skill does and when to use it
---

# Your Skill Name

## Instructions
Provide clear, step-by-step guidance for Claude.

## Examples
Show concrete examples of using this Skill.
```

For more details, see [Anthropic's Agent Skills Documentation](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills).

## Development

### Running Tests

```bash
# Start the server
uv run uvicorn backend.main:app --reload

# In another terminal, run tests
curl http://localhost:8000/health
```

### Database Reset

```bash
# Stop the server first, then:
rm data/agents.db
# Restart the server - it will recreate the database
```

## Architecture Principles

This project follows **SOLID principles**:

- **Single Responsibility**: Each module has one clear purpose (e.g., `skill_service.py` handles only skill management)
- **Open/Closed**: Easy to extend with new skill types without modifying existing code
- **Liskov Substitution**: Custom and Anthropic skills are interchangeable
- **Interface Segregation**: Separate endpoints for different concerns
- **Dependency Inversion**: Service layer abstracts Claude API details

## Version

**Current Version**: 0.2.0

### Recent Changes
- ✅ **WebSocket Real-Time Execution** (Issue #4)
  - WebSocket endpoint at `/ws/agents/{agent_id}/execute`
  - Real-time status updates during agent execution
  - Persistent connections for multiple executions
  - Foundation for future streaming capabilities
- ✅ Added Agent Skills support (custom and Anthropic pre-built)
- ✅ Skill-agent association system
- ✅ Execution tracking with skills_used field
- ✅ Optional skill enhancement (agents work with or without skills)

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Support

For issues or questions, please open an issue on GitHub.

## Roadmap

Future enhancements (post-MVP):
- Skill versioning
- Skill usage analytics
- Skill marketplace/sharing
- WebSocket streaming for real-time agent execution
- Frontend UI
- Multi-user support
