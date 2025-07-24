# BFCL Sample Synthesis using AWorld Runtime

This example demonstrates how to use AWorld to construct a runtime environment and synthesize function call samples for model training. The BFCL (Basic Function Call Learning) example shows how to create a virtual file system with MCP (Model Context Protocol) tools and generate training data from agent interactions.

## 📋 Overview

The BFCL example consists of:
- **GorillaFileSystem**: A virtual file system with MCP tools
- **Agent Runtime**: AWorld agent that interacts with the file system
- **Function Call Synthesis**: Generation of training samples from agent trajectories

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AWorld Agent  │───▶│  GorillaFileSystem│───▶│  MCP Tools      │
│                 │    │  (Virtual FS)     │    │  (pwd, ls, cd,  │
│ - LLM Provider  │    │                   │    │   touch, echo,  │
│ - MCP Client    │    │ - File/Directory  │    │   cat, etc.)    │
│ - Trajectory    │    │ - State Management│    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Trajectory     │    │  File System     │    │  Function Call  │
│  Collection     │    │  Operations      │    │  Samples        │
│                 │    │                   │    │                 │
│ - Agent Actions │    │ - Create/Read/   │    │ - Tool Calls    │
│ - Tool Calls    │    │   Write Files    │    │ - Parameters    │
│ - Results       │    │ - Directory      │    │ - Results       │
│                 │    │   Navigation     │    │ - Context       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Set your OpenRouter API key
export OPENROUTER_API_KEY="your-api-key-here"

# Navigate to the BFCL example
cd examples/BFCL
```

### 2. Run the Example

```bash
# Execute the file system agent
python run.py
```

### 3. Expected Output

The agent will:
1. Connect to the GorillaFileSystem MCP server
2. Perform file operations (create, read, write files)
3. Generate trajectory data with function calls
4. Display the results

## 📁 File Structure

```
examples/BFCL/
├── README.md                    # This file
├── run.py                      # Main agent runner
├── mcp_tools/
│   ├── __init__.py            # Package initialization
│   ├── gorilla_file_system.py # Virtual file system
│   └── test_server.py         # Function testing
└── requirements.txt            # Dependencies
```

## 🔧 Core Components

### 1. Agent Configuration (`run.py`)

```python
# Environment-based API key configuration
api_key = os.getenv('OPENROUTER_API_KEY')

agent_config = AgentConfig(
    llm_provider="openai",
    llm_model_name="openai/gpt-4o",
    llm_api_key=api_key,
    llm_base_url="https://openrouter.ai/api/v1"
)
```

### 2. MCP Server Configuration

```python
mcp_config = {
    "mcpServers": {
        "GorillaFileSystem": {
            "type": "sse",
            "url": "http://127.0.0.1:8000/sse/"
        }
    }
}
```

### 3. Agent Creation

```python
file_sys = Agent(
    conf=agent_config,
    name="file_sys_agent",
    system_prompt="You are a helpful agent to use the standard file system...",
    mcp_servers=["GorillaFileSystem"],
    mcp_config=mcp_config
)
```

### 4. Trajectory Collection

```python
result = Runners.sync_run(
    input="use mcp tools to perform file operations...",
    agent=file_sys
)
sample = result.trajectory  # Access trajectory data, which is a list of steps.
```

## 🛠️ MCP Tools (GorillaFileSystem)

The virtual file system provides the following MCP tools:

### File Operations
- `mcp_touch(file_name)`: Create a new file
- `mcp_echo(content, file_name)`: Write content to file
- `mcp_cat(file_name)`: Read file content
- `mcp_rm(file_name)`: Remove file

### Directory Operations
- `mcp_pwd()`: Get current directory
- `mcp_ls(a=False)`: List directory contents
- `mcp_cd(folder)`: Change directory
- `mcp_mkdir(dir_name)`: Create directory
- `mcp_rmdir(dir_name)`: Remove directory

### Advanced Operations
- `mcp_find(path, name)`: Search for files
- `mcp_wc(file_name, mode)`: Word count
- `mcp_sort(file_name)`: Sort file content
- `mcp_grep(file_name, pattern)`: Search in file
- `mcp_mv(source, destination)`: Move/rename
- `mcp_cp(source, destination)`: Copy files