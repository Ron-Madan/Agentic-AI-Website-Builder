# Setup Guide

## Quick Setup

### 1. Install Dependencies

```bash
python -m pip install -e .
```

This installs all required packages including FastAPI, OpenAI, Anthropic, SQLAlchemy, and more.

### 2. Configure (Optional)

Create a `.env` file:

```bash
# LLM Service (at least one recommended)
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...

# Deployment (optional)
NETLIFY_ACCESS_TOKEN=...
```

### 3. Run

```bash
# Option 1
make dev

# Option 2
python scripts/run_dev.py

# Option 3
uvicorn src.agentic_web_app_builder.api.main:app --reload
```

### 4. Access

Open: **http://localhost:8000**

## Verification

Test that everything is working:

```bash
python -c "from src.agentic_web_app_builder.api.main import app; print('✅ Setup complete!')"
```

## Troubleshooting

### Wrong Python Version

If you see import errors, ensure you're using the correct Python:

```bash
# Use the Python that has conda/anaconda
python -m pip install -e .
```

### Port Already in Use

```bash
uvicorn src.agentic_web_app_builder.api.main:app --reload --port 8001
```

### Missing Dependencies

```bash
python -m pip install -e . --force-reinstall
```

## What's Included

After installation, you have:

- ✅ FastAPI web server
- ✅ Multi-agent system (Planner, Developer, Tester, Monitor)
- ✅ LLM integration (OpenAI/Anthropic)
- ✅ Deployment tools (Netlify/Vercel)
- ✅ Testing framework
- ✅ Web UI

## Next Steps

1. Start the server
2. Open http://localhost:8000
3. Click "Create Your Website"
4. Describe your desired website
5. Watch the agents build it!
